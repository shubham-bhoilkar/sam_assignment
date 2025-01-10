from fastapi import FastAPI , HTTPException
from fastapi.responses import JSONResponse
from models import create_user ,update_user 
from user_api_function import view_records_logic
from caller import register_user_caller , update_user_caller , delete_user_caller
import logging
from logging.handlers import RotatingFileHandler
import configparser
import redis

def get_redis_client():
    return redis.StrictRedis(host="localhost", port=6379, decode_response=True)


config = configparser.ConfigParser()
config.read('/home/neuralit/shubham_workarea/python/microservice_application/config.ini')

host = config['Server']['host']
port = config['Server']['port']
log_file_path = config['Log']['file_path']
redis_host =config['Redis']['host']
redis_port =config['Redis']['port']
redis_db =config['Redis']['db']
redis_password = config['Redis'].get('password',None)

def setup_logging(file_path):
    logger = logging.getLogger('user_microservice')
    logger.setLevel(logging.DEBUG)
    file_handler = RotatingFileHandler(log_file_path, maxBytes=5*1024*1024, backupCount=5)
    file_handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )           
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger

logger = setup_logging(log_file_path)

# try:
#     redis_client =redis.Redis(host= redis_host, port =redis_port, db= redis_db,)

redis_client = get_redis_client()

app = FastAPI()

@app.get("/")
def main_page():
    return {"Welcome":"Here comes your demo home page"}

@app.on_event("startup")
def startup_event():
    try:
        redis_client.ping()
        logger.info("Connect to Redis successfully.")
    except redis.ConnectionError as e:
        logger.error(f"Failed to connect to Redis: {e}")
        raise

@app.on_event("shoutdown")
def shutdown_event():
    try:
        redis_client.close()
        logger.info("Redis connection closed.")
    except redis.ConnectionError as e:
        logger.error(f"Failed to close Redis connection. {e}")
        raise
def rate_limit(ip:str, limit: int = 5, window : int =60):
    key = f"rate_limit:{ip}"
    current_count = redis_client.incr(key)
    if current_count == 1:
        redis_client.expire(key, window)
    if current_count > limit:
         return False
    return True

@app.post("/register")
def register_user(user: create_user):
    try:
        ip = "user_ip_placeholder"
        if not rate_limit(ip):
            return JSONResponse(status_code= 429,
                                content={"status":"failure",
                                         "message":"Rate limit exceeded. Try again later."})
        result = register_user_caller(user, logger)
        if result:
            redis_client.set(f"user:{user.user_id}",user.json(),ex =3600)
            return JSONResponse(
                status_code=201,
                content ={"status":"success","message":user})
        else:
            return JSONResponse(
                status_code=400,
                content ={"status":"failure", "message": "User Creation request not sent to NSQ."})

    except Exception as e:
        logger.error(f"Error during user registration: {e}",exc_info =True)
        raise HTTPException(status_code= 500, detail="Internal Server Error.")

@app.get("/get_user_details/{user_id}")
def get_user_details(user_id: int):
    try:
        cached_data = redis_client.get(f"user:{user_id}")
        if cached_data:
            return JSONResponse(
                status_code=200,
                content={"status": "success", "data": cached_data}
            )
        records = view_records_logic(user_id, logger)
        
        if records:
            return JSONResponse(
                status_code=201,
                content= {"status": "success", "data": records}) 
        else:
            return JSONResponse(
                status_code=400,
                content={"status": "failure", "data": []})
        
    except Exception as e:
        logger.error(f"Error reading records from table 'user_details': {e}",exc_info =True)
        raise HTTPException(status_code=500, detail=f"Error reading records from table 'user_details'.")

@app.put("/update_user_details/{user_id}")
def update_user_details(user_id: int,user: update_user):
    try:
        result = update_user_caller(user, user_id, logger)
        if result:
            return JSONResponse(
                status_code=200,
                content ={"status": "success", "message": "user details updated."})
        else:
            return JSONResponse(
                status_code=400,
                content ={"status": "failure", "message": "user detail update failed."})
            
    except Exception as e:
        logger.error(f"Error during the update: {e}",exc_info =True)
        raise HTTPException(status_code = 500, detail="Internal Server Error.")

@app.delete("/delete_user/{user_id}")
def delete_user(user_id: int):
    try:
        result = delete_user_caller(user_id, logger)
        
        if result:
            return JSONResponse(
                status_code=201,
                content={"status": "success", "message": f"User with user_id {user_id} has been deleted."})
        else:
            return JSONResponse(
                status_code=400,
                content={"status": "failure", "message": f"No user found with user_id {user_id}."})
        
    except Exception as e:
        logger.error(f"Error deleting user with user_id {user_id}: {e}",exc_info =True)
        raise HTTPException(status_code=500, detail="Internal Server Error.")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app=app,host=host, port=eval(port))
    