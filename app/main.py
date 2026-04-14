from fastapi import FastAPI
from sqlalchemy import text
import random
import asyncio
from datetime import datetime
from fastapi.middleware.cors import CORSMiddleware
from app.database import engine, test_db_connection
from app.schemas import (
    UserCreate,
    LoginRequest,
    DepositRequest,
    WithdrawRequest,
    BuyRequest,
    SellRequest,
    CreateStockRequest,
    UpdateStockPriceRequest,
    MarketSettingsRequest,
    HolidayRequest,
)


def is_market_open(connection):
    now = datetime.now()

    if now.weekday() >= 5:
        return False

    holiday_result = connection.execute(
        text("""
            SELECT COUNT(*)
            FROM Holidays
            WHERE holiday_date = CAST(GETDATE() AS DATE)
        """)
    )
    holiday_count = holiday_result.fetchone()[0]

    if holiday_count > 0:
        return False

    market_result = connection.execute(
        text("""
            SELECT TOP 1 open_time, close_time
            FROM Market_Settings
            ORDER BY market_id DESC
        """)
    )
    market_row = market_result.fetchone()

    if market_row is None:
        open_hour = datetime.strptime("09:30:00", "%H:%M:%S").time()
        close_hour = datetime.strptime("16:00:00", "%H:%M:%S").time()
        return open_hour <= now.time() <= close_hour

    open_time = market_row[0]
    close_time = market_row[1]

    return open_time <= now.time() <= close_time


def update_stock_prices_once():
    with engine.begin() as connection:
        if not is_market_open(connection):
            return {"message": "Market is closed. No price update performed."}

        result = connection.execute(
            text("""
                SELECT stock_id, ticker, current_price, opening_price, daily_high, daily_low
                FROM Stocks
            """)
        )

        rows = result.fetchall()
        updated_stocks = []

        for row in rows:
            stock_id = row[0]
            ticker = row[1]
            current_price = float(row[2])
            opening_price = float(row[3]) if row[3] is not None else current_price
            daily_high = float(row[4]) if row[4] is not None else current_price
            daily_low = float(row[5]) if row[5] is not None else current_price

            random_percent_change = random.uniform(-0.01, 0.01)
            reversion_strength = 0.05
            mean_reversion = ((opening_price - current_price) / opening_price) * reversion_strength
            adjusted_percent_change = random_percent_change + mean_reversion
            new_price = current_price * (1 + adjusted_percent_change)

            if new_price < 1:
                new_price = 1.00

            new_price = round(new_price, 2)

            new_daily_high = max(daily_high, new_price)
            new_daily_low = min(daily_low, new_price)

            connection.execute(
                text("""
                    UPDATE Stocks
                    SET current_price = :new_price,
                        daily_high = :new_daily_high,
                        daily_low = :new_daily_low
                    WHERE stock_id = :stock_id
                """),
                {
                    "new_price": new_price,
                    "new_daily_high": new_daily_high,
                    "new_daily_low": new_daily_low,
                    "stock_id": stock_id
                }
            )

            updated_stocks.append({
                "stock_id": stock_id,
                "ticker": ticker,
                "old_price": current_price,
                "new_price": new_price
            })

        return {
            "message": "Stock prices updated successfully",
            "updated_stocks": updated_stocks
        }


async def market_price_updater():
    while True:
        try:
            result = update_stock_prices_once()
            print(result)
        except Exception as e:
            print("Price update error:", e)

        await asyncio.sleep(10)


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event():
    asyncio.create_task(market_price_updater())


@app.post("/admin/run-price-update")
def run_price_update():
    return update_stock_prices_once()


@app.get("/")
def root():
    return {"message": "Stock Trading API running"}


@app.get("/test-db")
def test_db():
    row = test_db_connection()
    return {"connected_database": row[0]}


@app.get("/test-users")
def test_users():
    with engine.connect() as connection:
        result = connection.execute(text("SELECT COUNT(*) AS total FROM Users"))
        row = result.fetchone()
        return {"users_in_db": row[0]}


@app.post("/register")
def register_user(user: UserCreate):
    with engine.begin() as connection:
        result = connection.execute(
            text("""
                INSERT INTO Users (full_name, username, email, password_hash, role)
                OUTPUT INSERTED.user_id
                VALUES (:full_name, :username, :email, :password_hash, :role)
            """),
            {
                "full_name": user.full_name,
                "username": user.username,
                "email": user.email,
                "password_hash": user.password_hash,
                "role": user.role
            }
        )

        new_user_id = result.fetchone()[0]

        if user.role.lower() == "user":
            connection.execute(
                text("""
                    INSERT INTO Portfolios (user_id, cash_balance, reserved_cash)
                    VALUES (:user_id, 0, 0)
                """),
                {"user_id": new_user_id}
            )

        elif user.role.lower() == "admin":
            connection.execute(
                text("""
                    INSERT INTO Administrators (user_id)
                    VALUES (:user_id)
                """),
                {"user_id": new_user_id}
            )

        return {
            "message": "User registered successfully",
            "user_id": new_user_id,
            "role": user.role
        }


@app.post("/login")
def login(request: LoginRequest):
    with engine.connect() as connection:
        result = connection.execute(
            text("""
                SELECT user_id, full_name, username, email, role
                FROM Users
                WHERE username = :username AND password_hash = :password
            """),
            {
                "username": request.username,
                "password": request.password
            }
        )

        row = result.fetchone()

        if row is None:
            return {"error": "Invalid username or password"}

        return {
            "message": "Login successful",
            "user_id": row[0],
            "full_name": row[1],
            "username": row[2],
            "email": row[3],
            "role": row[4]
        }


@app.get("/market/status")
def market_status():
    with engine.connect() as connection:
        return {"is_open": is_market_open(connection)}


@app.get("/market")
def get_market():
    with engine.connect() as connection:
        result = connection.execute(
            text("""
                SELECT
                    stock_id,
                    ticker,
                    company_name,
                    type,
                    current_price,
                    volume,
                    opening_price,
                    daily_high,
                    daily_low
                FROM Stocks
                ORDER BY ticker
            """)
        )

        rows = result.fetchall()
        market_data = []

        for row in rows:
            current_price = float(row[4])
            volume = row[5]

            market_data.append({
                "stock_id": row[0],
                "ticker": row[1],
                "company_name": row[2],
                "type": row[3],
                "current_price": current_price,
                "volume": volume,
                "market_cap": current_price * volume,
                "opening_price": float(row[6]) if row[6] is not None else None,
                "daily_high": float(row[7]) if row[7] is not None else None,
                "daily_low": float(row[8]) if row[8] is not None else None
            })

        return market_data


@app.get("/stocks")
def get_stocks():
    with engine.connect() as connection:
        result = connection.execute(text("""
            SELECT stock_id, ticker, company_name, type, current_price, volume,
                   opening_price, daily_high, daily_low
            FROM Stocks
            ORDER BY ticker
        """))
        rows = result.fetchall()

        stocks = []
        for row in rows:
            current_price = float(row[4])
            volume = row[5]

            stocks.append({
                "stock_id": row[0],
                "ticker": row[1],
                "company_name": row[2],
                "type": row[3],
                "current_price": current_price,
                "volume": volume,
                "market_cap": current_price * volume,
                "opening_price": float(row[6]) if row[6] is not None else None,
                "daily_high": float(row[7]) if row[7] is not None else None,
                "daily_low": float(row[8]) if row[8] is not None else None
            })

        return stocks


@app.post("/deposit")
def deposit_funds(request: DepositRequest):
    if request.amount <= 0:
        return {"error": "Deposit amount must be greater than 0"}

    with engine.begin() as connection:
        portfolio_result = connection.execute(
            text("""
                SELECT portfolio_id, cash_balance
                FROM Portfolios
                WHERE user_id = :user_id
            """),
            {"user_id": request.user_id}
        )

        portfolio_row = portfolio_result.fetchone()

        if portfolio_row is None:
            return {"error": "Portfolio not found for this user"}

        portfolio_id = portfolio_row[0]
        current_balance = float(portfolio_row[1])
        new_balance = current_balance + request.amount

        connection.execute(
            text("""
                UPDATE Portfolios
                SET cash_balance = :new_balance
                WHERE portfolio_id = :portfolio_id
            """),
            {
                "new_balance": new_balance,
                "portfolio_id": portfolio_id
            }
        )

        connection.execute(
            text("""
                INSERT INTO Transactions (portfolio_id, transaction_type, amount)
                VALUES (:portfolio_id, :transaction_type, :amount)
            """),
            {
                "portfolio_id": portfolio_id,
                "transaction_type": "deposit",
                "amount": request.amount
            }
        )

        return {
            "message": "Deposit successful",
            "user_id": request.user_id,
            "portfolio_id": portfolio_id,
            "deposited_amount": request.amount,
            "new_balance": new_balance
        }


@app.post("/withdraw")
def withdraw_funds(request: WithdrawRequest):
    if request.amount <= 0:
        return {"error": "Withdrawal amount must be greater than 0"}

    with engine.begin() as connection:
        portfolio_result = connection.execute(
            text("""
                SELECT portfolio_id, cash_balance
                FROM Portfolios
                WHERE user_id = :user_id
            """),
            {"user_id": request.user_id}
        )

        portfolio_row = portfolio_result.fetchone()

        if portfolio_row is None:
            return {"error": "Portfolio not found for this user"}

        portfolio_id = portfolio_row[0]
        current_balance = float(portfolio_row[1])

        if request.amount > current_balance:
            return {
                "error": "Insufficient funds",
                "current_balance": current_balance
            }

        new_balance = current_balance - request.amount

        connection.execute(
            text("""
                UPDATE Portfolios
                SET cash_balance = :new_balance
                WHERE portfolio_id = :portfolio_id
            """),
            {
                "new_balance": new_balance,
                "portfolio_id": portfolio_id
            }
        )

        connection.execute(
            text("""
                INSERT INTO Transactions (portfolio_id, transaction_type, amount)
                VALUES (:portfolio_id, :transaction_type, :amount)
            """),
            {
                "portfolio_id": portfolio_id,
                "transaction_type": "withdrawal",
                "amount": request.amount
            }
        )

        return {
            "message": "Withdrawal successful",
            "user_id": request.user_id,
            "portfolio_id": portfolio_id,
            "withdrawn_amount": request.amount,
            "new_balance": new_balance
        }


@app.get("/portfolio/{user_id}")
def get_portfolio(user_id: int):
    with engine.connect() as connection:
        portfolio_result = connection.execute(
            text("""
                SELECT portfolio_id, cash_balance, reserved_cash
                FROM Portfolios
                WHERE user_id = :user_id
            """),
            {"user_id": user_id}
        )

        portfolio_row = portfolio_result.fetchone()

        if portfolio_row is None:
            return {"error": "Portfolio not found for this user"}

        portfolio_id = portfolio_row[0]
        cash_balance = float(portfolio_row[1])
        reserved_cash = float(portfolio_row[2])

        positions_result = connection.execute(
            text("""
                SELECT p.stock_id, s.ticker, s.company_name, p.shares_owned, p.average_cost
                FROM Positions p
                JOIN Stocks s ON p.stock_id = s.stock_id
                WHERE p.portfolio_id = :portfolio_id
            """),
            {"portfolio_id": portfolio_id}
        )

        positions_rows = positions_result.fetchall()

        positions = []
        for row in positions_rows:
            positions.append({
                "stock_id": row[0],
                "ticker": row[1],
                "company_name": row[2],
                "shares_owned": row[3],
                "average_cost": float(row[4])
            })

        return {
            "user_id": user_id,
            "portfolio_id": portfolio_id,
            "cash_balance": cash_balance,
            "reserved_cash": reserved_cash,
            "positions": positions
        }


@app.get("/transactions/{user_id}")
def get_transactions(user_id: int):
    with engine.connect() as connection:
        portfolio_result = connection.execute(
            text("""
                SELECT portfolio_id
                FROM Portfolios
                WHERE user_id = :user_id
            """),
            {"user_id": user_id}
        )

        portfolio_row = portfolio_result.fetchone()

        if portfolio_row is None:
            return {"error": "Portfolio not found for this user"}

        portfolio_id = portfolio_row[0]

        tx_result = connection.execute(
            text("""
                SELECT transaction_id, transaction_type, amount, created_at
                FROM Transactions
                WHERE portfolio_id = :portfolio_id
                ORDER BY created_at DESC
            """),
            {"portfolio_id": portfolio_id}
        )

        tx_rows = tx_result.fetchall()

        transactions = []
        for row in tx_rows:
            transactions.append({
                "transaction_id": row[0],
                "transaction_type": row[1],
                "amount": float(row[2]),
                "created_at": str(row[3])
            })

        return {
            "user_id": user_id,
            "portfolio_id": portfolio_id,
            "transactions": transactions
        }


@app.get("/orders/{user_id}")
def get_orders(user_id: int):
    with engine.connect() as connection:
        portfolio_result = connection.execute(
            text("""
                SELECT portfolio_id
                FROM Portfolios
                WHERE user_id = :user_id
            """),
            {"user_id": user_id}
        )

        portfolio_row = portfolio_result.fetchone()

        if portfolio_row is None:
            return {"error": "Portfolio not found for this user"}

        portfolio_id = portfolio_row[0]

        result = connection.execute(
            text("""
                SELECT
                    o.order_id,
                    o.order_type,
                    o.quantity,
                    o.price_at_order,
                    o.status,
                    o.created_at,
                    s.ticker,
                    s.company_name
                FROM Orders o
                JOIN Stocks s ON o.stock_id = s.stock_id
                WHERE o.portfolio_id = :portfolio_id
                ORDER BY o.created_at DESC
            """),
            {"portfolio_id": portfolio_id}
        )

        rows = result.fetchall()

        orders = []
        for row in rows:
            orders.append({
                "order_id": row[0],
                "order_type": row[1],
                "quantity": float(row[2]),
                "price_at_order": float(row[3]),
                "status": row[4],
                "created_at": str(row[5]),
                "ticker": row[6],
                "company_name": row[7]
            })

        return {
            "user_id": user_id,
            "portfolio_id": portfolio_id,
            "orders": orders
        }


@app.get("/positions/{user_id}")
def get_positions(user_id: int):
    with engine.connect() as connection:
        portfolio_result = connection.execute(
            text("""
                SELECT portfolio_id
                FROM Portfolios
                WHERE user_id = :user_id
            """),
            {"user_id": user_id}
        )

        portfolio_row = portfolio_result.fetchone()

        if portfolio_row is None:
            return {"error": "Portfolio not found for this user"}

        portfolio_id = portfolio_row[0]

        positions_result = connection.execute(
            text("""
                SELECT
                    p.position_id,
                    p.stock_id,
                    s.ticker,
                    s.company_name,
                    p.shares_owned,
                    p.average_cost,
                    s.current_price
                FROM Positions p
                JOIN Stocks s ON p.stock_id = s.stock_id
                WHERE p.portfolio_id = :portfolio_id
            """),
            {"portfolio_id": portfolio_id}
        )

        rows = positions_result.fetchall()
        positions = []

        for row in rows:
            position_id = row[0]
            stock_id = row[1]
            ticker = row[2]
            company_name = row[3]
            shares_owned = int(row[4])
            average_cost = float(row[5])
            current_price = float(row[6])

            market_value = shares_owned * current_price
            unrealized_pnl = (current_price - average_cost) * shares_owned

            positions.append({
                "position_id": position_id,
                "stock_id": stock_id,
                "ticker": ticker,
                "company_name": company_name,
                "shares_owned": shares_owned,
                "average_cost": average_cost,
                "current_price": current_price,
                "market_value": market_value,
                "unrealized_pnl": unrealized_pnl
            })

        return {
            "user_id": user_id,
            "portfolio_id": portfolio_id,
            "positions": positions
        }


@app.post("/buy")
def buy_stock(request: BuyRequest):
    if request.quantity <= 0:
        return {"error": "Quantity must be greater than 0"}

    with engine.begin() as connection:
        if not is_market_open(connection):
            return {"error": "Market is currently closed"}

        portfolio_result = connection.execute(
            text("""
                SELECT portfolio_id, cash_balance
                FROM Portfolios
                WHERE user_id = :user_id
            """),
            {"user_id": request.user_id}
        )

        portfolio_row = portfolio_result.fetchone()

        if portfolio_row is None:
            return {"error": "Portfolio not found for this user"}

        portfolio_id = portfolio_row[0]
        cash_balance = float(portfolio_row[1])

        stock_result = connection.execute(
            text("""
                SELECT stock_id, ticker, company_name, current_price
                FROM Stocks
                WHERE stock_id = :stock_id
            """),
            {"stock_id": request.stock_id}
        )

        stock_row = stock_result.fetchone()

        if stock_row is None:
            return {"error": "Stock not found"}

        stock_id = stock_row[0]
        ticker = stock_row[1]
        company_name = stock_row[2]
        current_price = float(stock_row[3])

        total_cost = current_price * request.quantity

        if total_cost > cash_balance:
            return {
                "error": "Insufficient funds",
                "cash_balance": cash_balance,
                "required_amount": total_cost
            }

        order_result = connection.execute(
            text("""
                INSERT INTO Orders (portfolio_id, stock_id, order_type, quantity, price_at_order, status)
                OUTPUT INSERTED.order_id
                VALUES (:portfolio_id, :stock_id, :order_type, :quantity, :price_at_order, :status)
            """),
            {
                "portfolio_id": portfolio_id,
                "stock_id": stock_id,
                "order_type": "buy",
                "quantity": request.quantity,
                "price_at_order": current_price,
                "status": "filled"
            }
        )

        order_id = order_result.fetchone()[0]

        connection.execute(
            text("""
                INSERT INTO Trades (order_id, execution_price, quantity)
                VALUES (:order_id, :execution_price, :quantity)
            """),
            {
                "order_id": order_id,
                "execution_price": current_price,
                "quantity": request.quantity
            }
        )

        position_result = connection.execute(
            text("""
                SELECT position_id, shares_owned, average_cost
                FROM Positions
                WHERE portfolio_id = :portfolio_id AND stock_id = :stock_id
            """),
            {
                "portfolio_id": portfolio_id,
                "stock_id": stock_id
            }
        )

        position_row = position_result.fetchone()

        if position_row is None:
            connection.execute(
                text("""
                    INSERT INTO Positions (portfolio_id, stock_id, shares_owned, average_cost)
                    VALUES (:portfolio_id, :stock_id, :shares_owned, :average_cost)
                """),
                {
                    "portfolio_id": portfolio_id,
                    "stock_id": stock_id,
                    "shares_owned": request.quantity,
                    "average_cost": current_price
                }
            )
        else:
            position_id = position_row[0]
            old_shares = int(position_row[1])
            old_avg_cost = float(position_row[2])

            new_total_shares = old_shares + request.quantity
            new_avg_cost = ((old_shares * old_avg_cost) + (request.quantity * current_price)) / new_total_shares

            connection.execute(
                text("""
                    UPDATE Positions
                    SET shares_owned = :shares_owned,
                        average_cost = :average_cost
                    WHERE position_id = :position_id
                """),
                {
                    "shares_owned": new_total_shares,
                    "average_cost": new_avg_cost,
                    "position_id": position_id
                }
            )

        new_balance = cash_balance - total_cost

        connection.execute(
            text("""
                UPDATE Portfolios
                SET cash_balance = :new_balance
                WHERE portfolio_id = :portfolio_id
            """),
            {
                "new_balance": new_balance,
                "portfolio_id": portfolio_id
            }
        )

        connection.execute(
            text("""
                INSERT INTO Transactions (portfolio_id, transaction_type, amount)
                VALUES (:portfolio_id, :transaction_type, :amount)
            """),
            {
                "portfolio_id": portfolio_id,
                "transaction_type": "buy",
                "amount": total_cost
            }
        )

        return {
            "message": "Buy order executed successfully",
            "user_id": request.user_id,
            "portfolio_id": portfolio_id,
            "order_id": order_id,
            "stock_id": stock_id,
            "ticker": ticker,
            "company_name": company_name,
            "quantity": request.quantity,
            "price": current_price,
            "total_cost": total_cost,
            "new_balance": new_balance
        }


@app.post("/sell")
def sell_stock(request: SellRequest):
    if request.quantity <= 0:
        return {"error": "Quantity must be greater than 0"}

    with engine.begin() as connection:
        if not is_market_open(connection):
            return {"error": "Market is currently closed"}

        portfolio_result = connection.execute(
            text("""
                SELECT portfolio_id, cash_balance
                FROM Portfolios
                WHERE user_id = :user_id
            """),
            {"user_id": request.user_id}
        )

        portfolio_row = portfolio_result.fetchone()

        if portfolio_row is None:
            return {"error": "Portfolio not found for this user"}

        portfolio_id = portfolio_row[0]
        cash_balance = float(portfolio_row[1])

        stock_result = connection.execute(
            text("""
                SELECT stock_id, ticker, company_name, current_price
                FROM Stocks
                WHERE stock_id = :stock_id
            """),
            {"stock_id": request.stock_id}
        )

        stock_row = stock_result.fetchone()

        if stock_row is None:
            return {"error": "Stock not found"}

        stock_id = stock_row[0]
        ticker = stock_row[1]
        company_name = stock_row[2]
        current_price = float(stock_row[3])

        position_result = connection.execute(
            text("""
                SELECT position_id, shares_owned, average_cost
                FROM Positions
                WHERE portfolio_id = :portfolio_id AND stock_id = :stock_id
            """),
            {
                "portfolio_id": portfolio_id,
                "stock_id": stock_id
            }
        )

        position_row = position_result.fetchone()

        if position_row is None:
            return {"error": "User does not own this stock"}

        position_id = position_row[0]
        shares_owned = int(position_row[1])

        if request.quantity > shares_owned:
            return {
                "error": "Insufficient shares",
                "shares_owned": shares_owned
            }

        total_proceeds = current_price * request.quantity

        order_result = connection.execute(
            text("""
                INSERT INTO Orders (portfolio_id, stock_id, order_type, quantity, price_at_order, status)
                OUTPUT INSERTED.order_id
                VALUES (:portfolio_id, :stock_id, :order_type, :quantity, :price_at_order, :status)
            """),
            {
                "portfolio_id": portfolio_id,
                "stock_id": stock_id,
                "order_type": "sell",
                "quantity": request.quantity,
                "price_at_order": current_price,
                "status": "filled"
            }
        )

        order_id = order_result.fetchone()[0]

        connection.execute(
            text("""
                INSERT INTO Trades (order_id, execution_price, quantity)
                VALUES (:order_id, :execution_price, :quantity)
            """),
            {
                "order_id": order_id,
                "execution_price": current_price,
                "quantity": request.quantity
            }
        )

        new_share_count = shares_owned - request.quantity

        if new_share_count == 0:
            connection.execute(
                text("""
                    DELETE FROM Positions
                    WHERE position_id = :position_id
                """),
                {"position_id": position_id}
            )
        else:
            connection.execute(
                text("""
                    UPDATE Positions
                    SET shares_owned = :shares_owned
                    WHERE position_id = :position_id
                """),
                {
                    "shares_owned": new_share_count,
                    "position_id": position_id
                }
            )

        new_balance = cash_balance + total_proceeds

        connection.execute(
            text("""
                UPDATE Portfolios
                SET cash_balance = :new_balance
                WHERE portfolio_id = :portfolio_id
            """),
            {
                "new_balance": new_balance,
                "portfolio_id": portfolio_id
            }
        )

        connection.execute(
            text("""
                INSERT INTO Transactions (portfolio_id, transaction_type, amount)
                VALUES (:portfolio_id, :transaction_type, :amount)
            """),
            {
                "portfolio_id": portfolio_id,
                "transaction_type": "sell",
                "amount": total_proceeds
            }
        )

        return {
            "message": "Sell order executed successfully",
            "user_id": request.user_id,
            "portfolio_id": portfolio_id,
            "order_id": order_id,
            "stock_id": stock_id,
            "ticker": ticker,
            "company_name": company_name,
            "quantity_sold": request.quantity,
            "price": current_price,
            "total_proceeds": total_proceeds,
            "remaining_shares": new_share_count,
            "new_balance": new_balance
        }


@app.post("/admin/stocks")
def create_stock(request: CreateStockRequest):
    with engine.begin() as connection:
        admin_result = connection.execute(
            text("""
                SELECT a.admin_id
                FROM Administrators a
                JOIN Users u ON a.user_id = u.user_id
                WHERE u.username = :username
            """),
            {"username": request.admin_username}
        )

        admin_row = admin_result.fetchone()

        if admin_row is None:
            return {"error": "Admin user not found"}

        admin_id = admin_row[0]

        result = connection.execute(
            text("""
                INSERT INTO Stocks (
                    ticker,
                    company_name,
                    current_price,
                    volume,
                    opening_price,
                    daily_high,
                    daily_low,
                    admin_id
                )
                OUTPUT INSERTED.stock_id
                VALUES (
                    :ticker,
                    :company_name,
                    :price,
                    :volume,
                    :price,
                    :price,
                    :price,
                    :admin_id
                )
            """),
            {
                "ticker": request.ticker,
                "company_name": request.company_name,
                "price": request.initial_price,
                "volume": request.volume,
                "admin_id": admin_id
            }
        )

        stock_id = result.fetchone()[0]

        return {
            "message": "Stock created successfully",
            "stock_id": stock_id,
            "created_by_admin": request.admin_username,
            "ticker": request.ticker,
            "price": request.initial_price
        }


@app.put("/admin/stocks/{stock_id}")
def update_stock_price(stock_id: int, request: UpdateStockPriceRequest):
    if request.new_price <= 0:
        return {"error": "New price must be greater than 0"}

    with engine.begin() as connection:
        stock_result = connection.execute(
            text("""
                SELECT stock_id, ticker, company_name, current_price, daily_high, daily_low
                FROM Stocks
                WHERE stock_id = :stock_id
            """),
            {"stock_id": stock_id}
        )

        stock_row = stock_result.fetchone()

        if stock_row is None:
            return {"error": "Stock not found"}

        ticker = stock_row[1]
        company_name = stock_row[2]
        old_price = float(stock_row[3])
        old_high = float(stock_row[4]) if stock_row[4] is not None else old_price
        old_low = float(stock_row[5]) if stock_row[5] is not None else old_price

        new_high = max(old_high, request.new_price)
        new_low = min(old_low, request.new_price)

        connection.execute(
            text("""
                UPDATE Stocks
                SET current_price = :new_price,
                    daily_high = :new_high,
                    daily_low = :new_low
                WHERE stock_id = :stock_id
            """),
            {
                "new_price": request.new_price,
                "new_high": new_high,
                "new_low": new_low,
                "stock_id": stock_id
            }
        )

        return {
            "message": "Stock price updated successfully",
            "stock_id": stock_id,
            "ticker": ticker,
            "company_name": company_name,
            "old_price": old_price,
            "new_price": request.new_price,
            "daily_high": new_high,
            "daily_low": new_low
        }


@app.get("/admin/market-settings")
def get_market_settings():
    with engine.connect() as connection:
        result = connection.execute(
            text("""
                SELECT TOP 1 market_id, open_time, close_time
                FROM Market_Settings
                ORDER BY market_id DESC
            """)
        )
        row = result.fetchone()

        if row is None:
            return {
                "open_time": "09:30:00",
                "close_time": "16:00:00",
                "source": "default"
            }

        return {
            "market_id": row[0],
            "open_time": str(row[1]),
            "close_time": str(row[2]),
            "source": "database"
        }


@app.put("/admin/market-settings")
def update_market_settings(request: MarketSettingsRequest):
    with engine.begin() as connection:
        result = connection.execute(
            text("""
                INSERT INTO Market_Settings (open_time, close_time)
                OUTPUT INSERTED.market_id
                VALUES (:open_time, :close_time)
            """),
            {"open_time": request.open_time, "close_time": request.close_time}
        )
        new_id = result.fetchone()[0]

        return {
            "message": "Market hours updated successfully",
            "market_id": new_id,
            "open_time": request.open_time,
            "close_time": request.close_time
        }


@app.get("/admin/holidays")
def get_holidays():
    with engine.connect() as connection:
        result = connection.execute(
            text("""
                SELECT holiday_date, holiday_name
                FROM Holidays
                ORDER BY holiday_date ASC
            """)
        )
        rows = result.fetchall()

        holidays = []
        for row in rows:
            holidays.append({
                "holiday_date": str(row[0]),
                "holiday_name": row[1] if row[1] is not None else ""
            })

        return {"holidays": holidays}


@app.post("/admin/holidays")
def add_holiday(request: HolidayRequest):
    with engine.begin() as connection:
        exists = connection.execute(
            text("SELECT COUNT(*) FROM Holidays WHERE holiday_date = :d"),
            {"d": request.holiday_date}
        ).fetchone()[0]

        if exists:
            return {"error": f"{request.holiday_date} is already marked as a holiday"}

        connection.execute(
            text("""
                INSERT INTO Holidays (holiday_date, holiday_name)
                VALUES (:holiday_date, :holiday_name)
            """),
            {
                "holiday_date": request.holiday_date,
                "holiday_name": request.holiday_name or ""
            }
        )

        return {
            "message": "Holiday added successfully",
            "holiday_date": request.holiday_date,
            "holiday_name": request.holiday_name or ""
        }


@app.delete("/admin/holidays/{holiday_date}")
def delete_holiday(holiday_date: str):
    with engine.begin() as connection:
        result = connection.execute(
            text("DELETE FROM Holidays WHERE holiday_date = :d"),
            {"d": holiday_date}
        )

        if result.rowcount == 0:
            return {"error": f"No holiday found for date {holiday_date}"}

        return {"message": f"Holiday {holiday_date} removed successfully"}
      
