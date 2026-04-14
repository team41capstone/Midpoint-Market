-- ============================================================
--  Midpoint Markets — T-SQL Schema (SQL Server / SSMS 22)
-- ============================================================

-- Users
CREATE TABLE Users (
    user_id       INT           IDENTITY(1,1) PRIMARY KEY,
    full_name     VARCHAR(100)  NOT NULL,
    username      VARCHAR(50)   NOT NULL UNIQUE,
    email         VARCHAR(150)  NOT NULL UNIQUE,
    password_hash VARCHAR(255)  NOT NULL,
    role          VARCHAR(10)   NOT NULL DEFAULT 'user'
                                CONSTRAINT chk_users_role CHECK (role IN ('user', 'admin')),
    created_at    DATETIME      NOT NULL DEFAULT GETDATE()
);

-- Administrators
CREATE TABLE Administrators (
    admin_id   INT      IDENTITY(1,1) PRIMARY KEY,
    user_id    INT      NOT NULL UNIQUE,
    created_at DATETIME NOT NULL DEFAULT GETDATE(),
    CONSTRAINT fk_admin_user FOREIGN KEY (user_id)
        REFERENCES Users(user_id) ON DELETE CASCADE
);

-- Stocks
CREATE TABLE Stocks (
    stock_id      INT            IDENTITY(1,1) PRIMARY KEY,
    ticker        VARCHAR(10)    NOT NULL UNIQUE,
    company_name  VARCHAR(150)   NOT NULL,
    type          VARCHAR(20)    NOT NULL DEFAULT 'Other'
                                 CONSTRAINT chk_stocks_type CHECK (type IN (
                                     'Tech','Finance','Crypto','Energy',
                                     'Healthcare','Food','Retail','Auto',
                                     'Media','Real Estate','Industrial','Other'
                                 )),
    current_price DECIMAL(18,4)  NOT NULL DEFAULT 0.0000,
    opening_price DECIMAL(18,4)  NOT NULL DEFAULT 0.0000,
    daily_high    DECIMAL(18,4)  NOT NULL DEFAULT 0.0000,
    daily_low     DECIMAL(18,4)  NOT NULL DEFAULT 0.0000,
    volume        BIGINT         NOT NULL DEFAULT 0,
    admin_id      INT            NULL,
    CONSTRAINT fk_stocks_admin FOREIGN KEY (admin_id)
        REFERENCES Administrators(admin_id) ON DELETE SET NULL
);

-- Portfolios
CREATE TABLE Portfolios (
    portfolio_id  INT           IDENTITY(1,1) PRIMARY KEY,
    user_id       INT           NOT NULL UNIQUE,
    cash_balance  DECIMAL(18,4) NOT NULL DEFAULT 0.0000,
    reserved_cash DECIMAL(18,4) NOT NULL DEFAULT 0.0000,
    created_at    DATETIME      NOT NULL DEFAULT GETDATE(),
    CONSTRAINT fk_portfolios_user FOREIGN KEY (user_id)
        REFERENCES Users(user_id) ON DELETE CASCADE
);

-- Positions
CREATE TABLE Positions (
    position_id  INT           IDENTITY(1,1) PRIMARY KEY,
    portfolio_id INT           NOT NULL,
    stock_id     INT           NOT NULL,
    shares_owned DECIMAL(18,8) NOT NULL DEFAULT 0.00000000,
    average_cost DECIMAL(18,4) NOT NULL DEFAULT 0.0000,
    CONSTRAINT uq_portfolio_stock UNIQUE (portfolio_id, stock_id),
    CONSTRAINT fk_positions_portfolio FOREIGN KEY (portfolio_id)
        REFERENCES Portfolios(portfolio_id) ON DELETE CASCADE,
    CONSTRAINT fk_positions_stock FOREIGN KEY (stock_id)
        REFERENCES Stocks(stock_id) ON DELETE CASCADE
);

-- Transactions
CREATE TABLE Transactions (
    transaction_id   INT           IDENTITY(1,1) PRIMARY KEY,
    portfolio_id     INT           NOT NULL,
    transaction_type VARCHAR(15)   NOT NULL
                                   CONSTRAINT chk_txn_type CHECK (transaction_type IN (
                                       'deposit','withdrawal','buy','sell'
                                   )),
    amount           DECIMAL(18,4) NOT NULL,
    created_at       DATETIME      NOT NULL DEFAULT GETDATE(),
    CONSTRAINT fk_txn_portfolio FOREIGN KEY (portfolio_id)
        REFERENCES Portfolios(portfolio_id) ON DELETE CASCADE
);

-- Orders
CREATE TABLE Orders (
    order_id       INT           IDENTITY(1,1) PRIMARY KEY,
    portfolio_id   INT           NOT NULL,
    stock_id       INT           NOT NULL,
    order_type     VARCHAR(10)   NOT NULL
                                 CONSTRAINT chk_order_type CHECK (order_type IN (
                                     'market','limit','stop'
                                 )),
    quantity       DECIMAL(18,8) NOT NULL,
    price_at_order DECIMAL(18,4) NOT NULL,
    status         VARCHAR(10)   NOT NULL DEFAULT 'pending'
                                 CONSTRAINT chk_order_status CHECK (status IN (
                                     'pending','filled','cancelled','rejected'
                                 )),
    created_at     DATETIME      NOT NULL DEFAULT GETDATE(),
    CONSTRAINT fk_orders_portfolio FOREIGN KEY (portfolio_id)
        REFERENCES Portfolios(portfolio_id) ON DELETE CASCADE,
    CONSTRAINT fk_orders_stock FOREIGN KEY (stock_id)
        REFERENCES Stocks(stock_id) ON DELETE NO ACTION
);

-- Trades
CREATE TABLE Trades (
    trade_id        INT           IDENTITY(1,1) PRIMARY KEY,
    order_id        INT           NOT NULL UNIQUE,
    execution_price DECIMAL(18,4) NOT NULL,
    execution_time  DATETIME      NOT NULL DEFAULT GETDATE(),
    quantity        DECIMAL(18,8) NOT NULL,
    CONSTRAINT fk_trades_order FOREIGN KEY (order_id)
        REFERENCES Orders(order_id) ON DELETE CASCADE
);

-- Market Settings
CREATE TABLE Market_Settings (
    market_id           INT      IDENTITY(1,1) PRIMARY KEY,
    open_time           TIME     NOT NULL DEFAULT '09:30:00',
    close_time          TIME     NOT NULL DEFAULT '16:00:00',
    updated_by_admin_id INT      NULL,
    updated_at          DATETIME NOT NULL DEFAULT GETDATE(),
    CONSTRAINT fk_mkt_admin FOREIGN KEY (updated_by_admin_id)
        REFERENCES Administrators(admin_id) ON DELETE SET NULL
);

-- Holidays
CREATE TABLE Holidays (
    holiday_id          INT          IDENTITY(1,1) PRIMARY KEY,
    holiday_date        DATE         NOT NULL UNIQUE,
    holiday_name        VARCHAR(100) NOT NULL,
    created_by_admin_id INT          NULL,
    CONSTRAINT fk_holidays_admin FOREIGN KEY (created_by_admin_id)
        REFERENCES Administrators(admin_id) ON DELETE SET NULL
);