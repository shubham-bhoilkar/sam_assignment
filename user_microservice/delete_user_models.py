from pydantic import BaseModel

class delete_user(BaseModel):
    user_id : int
    first_name : str
    last_name : str
    phone: int
    email: str
    designation : str