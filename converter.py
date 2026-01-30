import mysql.connector
import pandas as pd

conn = mysql.connector.connect(
    host="localhost",
    user="root",
    password="sumo@123",
    database="rajya_sabha"
)


tables = [
    
    "member_special_mentions"
]

for table in tables:
    df = pd.read_sql(f"SELECT * FROM {table}", conn)
    df.to_csv(f"{table}.csv", index=False)
    print(f"{table}.csv exported")
