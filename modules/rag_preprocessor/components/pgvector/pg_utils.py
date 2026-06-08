
import psycopg2
import uuid

# # Funciones para manejar las colecciones de documentos
def create_collection_table(connection_string: str, table_name: str):
    with psycopg2.connect(connection_string) as conn:
        with conn.cursor() as cursor:
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {table_name} (
                    collection_uuid UUID PRIMARY KEY,
                    cmetadata JSON,
                    name VARCHAR(255) NOT NULL UNIQUE
                );
            """)
            conn.commit()

def add_collection(connection_string: str, table_name: str, collection_name: str, collection_uuid: uuid):
    with psycopg2.connect(connection_string) as conn:
        with conn.cursor() as cursor:
            if collection_uuid is not None:
                cursor.execute(f"""
                    INSERT INTO {table_name} (collection_uuid, name, cmetadata)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (name) DO UPDATE
                        SET collection_uuid = EXCLUDED.collection_uuid
                    RETURNING collection_uuid;
                """, (collection_uuid, collection_name, '{}'))
            else:
                cursor.execute(f"""
                    INSERT INTO {table_name} (name, cmetadata)
                    VALUES (%s, %s)
                    ON CONFLICT (name) DO NOTHING
                    RETURNING collection_uuid;
                """, (collection_name, '{}'))
            result = cursor.fetchone()
            conn.commit()
            # Si no se insertó porque ya existía, obtener el uuid existente
            if result is None:
                cursor.execute(f"SELECT collection_uuid FROM {table_name} WHERE name = %s;", (collection_name,))
                result = cursor.fetchone()
            return result[0] if result else None

def get_collection(connection_string: str, table_name: str, collection_name: str):
    with psycopg2.connect(connection_string) as conn:
        with conn.cursor() as cursor:
            cursor.execute(f"""
                SELECT * FROM {table_name} WHERE name = %s;
            """, (collection_name,))
            return cursor.fetchone()
    
## Embeddings
def create_embeddings_table(connection_string: str, table_name: str, collection_table: str):
    with psycopg2.connect(connection_string) as conn:
        with conn.cursor() as cursor:
            # Crear la tabla particionada por collection_uuid
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {table_name} (
                    collection_uuid UUID NOT NULL,
                    doc_id UUID NOT NULL,
                    embedding VECTOR(1536),
                    cmetadata JSONB,
                    id VARCHAR(255) NOT NULL,
                    document VARCHAR,
                    CONSTRAINT pk_{table_name} PRIMARY KEY (collection_uuid, id),
                    CONSTRAINT fk_collection
                        FOREIGN KEY(collection_uuid) REFERENCES {collection_table}(uuid)
                ) PARTITION BY HASH (collection_uuid);
            """)
            conn.commit()

import uuid
def get_partition_remainder(uuid_str, num_partitions=4):
    return uuid.UUID(uuid_str).int % num_partitions

def create_partitions(connection_string: str, table_name: str, num_partitions: int = 4):
    with psycopg2.connect(connection_string) as conn:
        with conn.cursor() as cursor:
            for remainder in range(num_partitions):
                cursor.execute(f"""
                    CREATE TABLE IF NOT EXISTS {table_name}_{remainder} PARTITION OF {table_name}
                    FOR VALUES WITH (MODULUS {num_partitions}, REMAINDER {remainder});
                """)
            conn.commit()


if __name__ == "__main__":
    # Example usage
    user = "your_user"
    password = "your_password"
    host = "localhost"
    port = 5432
    dbname = "your_db"
    sslmode = "disable"
    table_name = "collections"
    connection_string = f"postgresql://{user}:{password}@{host}:{port}/{dbname}?sslmode={sslmode}"
    # Create collection table
    create_collection_table(table_name="test_collection")
    create_embeddings_table(table_name="test_embeddings", collection_table="test_collection")
    create_partitions(table_name="test_embeddings", num_partitions=4)
    # Añadimos dos proyectos de ejemplo
    add_collection(table_name="test_collection", collection_name="Proyecto Manhattan")
    add_collection(table_name="test_collection", collection_name="Proyecto Mayhem")