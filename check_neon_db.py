import psycopg2

conn = psycopg2.connect(
    "postgresql://neondb_owner:npg_3FjdGVT4kAsL@ep-lively-shadow-a4yeiqni-pooler.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
)
cur = conn.cursor()

# Check all tables
cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public';")
tables = cur.fetchall()
print("Tables in DB:", tables)

# Check first 5 rows from each table
for table in tables:
    tname = table[0]
    cur.execute(f"SELECT * FROM {tname} LIMIT 5;")
    rows = cur.fetchall()
    print(f"\nFirst 5 rows of {tname}:")
    for row in rows:
        print(row)

conn.close()
