from pydantic import BaseModel, EmailStr
from datetime import time, date


class UserCreate(BaseModel):
    full_name: str
    username: str
    email: EmailStr
    password_hash: str
    role: str


class LoginRequest(BaseModel):
    username: str
    password: str


class DepositRequest(BaseModel):
    user_id: int
    amount: float


class WithdrawRequest(BaseModel):
    user_id: int
    amount: float


class BuyRequest(BaseModel):
    user_id: int
    stock_id: int
    quantity: int


class SellRequest(BaseModel):
    user_id: int
    stock_id: int
    quantity: int


class CreateStockRequest(BaseModel):
    admin_username: str
    ticker: str
    company_name: str
    initial_price: float
    volume: int


class UpdateStockPriceRequest(BaseModel):
    new_price: float


class MarketSettingsRequest(BaseModel):
    open_time: time
    close_time: time


class HolidayRequest(BaseModel):
    holiday_date: date
    holiday_name: str | None = None