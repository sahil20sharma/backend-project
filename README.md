This project contains the backend for the Organization Management Service.  
Follow the steps below to set up the application on your local system.

---

## 1. Clone the Repository
Clone the project and move into the project folder:

``` bash                           (multi line comment)
git clone <repository-link>
cd backend-project

Now ,create a virtual environemt and activate it :-
python3 -m venv venv
source venv/bin/activate

Now, install all required dependencies 
pip install -r requirements.txt
 
this project using mongodb as a database so,
sudo systemctl start mongod (if installed)
 
 and can check status using- sudo systemctl status mongod

 Now, Run the server :- 
 uvicorn main:app --reload --host 0.0.0.0 --port 8000

 TESTING APIS USING CURL:-

You can interact with the APIs using curl .\
 (sending post request for creating admin account using curl where H is using for sending headers and d for data).
curl -X POST "http://localhost:8000/org/create" \ 
-H "Content-Type: application/json" \
-d '{"organization_name": "TestOrg", "email": "admin@test.com", "password": "secret123"}'

Get Organization Details:-
curl "http://localhost:8000/org/get?organization_name=TestOrg"

Once the server is running, API documentation will available at:
http://localhost:8000/docs# backend-project
