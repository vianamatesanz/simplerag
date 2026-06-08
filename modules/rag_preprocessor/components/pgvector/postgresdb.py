import psycopg2
from typing import List, Dict, Any
from abc import ABC

class PostgresDB:
    def __init__(self, host, dbname, user, password, sslmode, port):
        self.host = host
        self.dbname = dbname
        self.user = user
        self.password = password
        self.sslmode = sslmode
        self.port = port
        self.conn = None

    def connect(self):
        try:
            self.conn = psycopg2.connect(
                host=self.host,
                dbname=self.dbname,
                user=self.user,
                password=self.password,
                sslmode=self.sslmode,
                port=self.port
            )
            print("Conexión exitosa a Azure PostgreSQL")


        except Exception as e:
            print("Error de conexión:", e)

    def get_connection_string(self) -> str:
        """Genera la cadena de conexión para la base de datos."""
        if not self.conn:
            raise ValueError("No hay conexión activa. Por favor, llama a connect() primero.")
        return (
            f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.dbname}"
            f"?sslmode={self.sslmode}"
        )
    
    def disconnect(self):
        if self.conn:
            self.conn.close()
            print("Conexión cerrada.")
        else:
            print("No hay conexión activa para cerrar.")
    
    def get_info(self):
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public';")
            tables = cursor.fetchall()
            info = [{"table_name": table[0]} for table in tables]
            cursor.close()
            return info
        except Exception as e:
            print("Error al obtener información de las tablas:", e)
            return []
        
    def execute_query(self, query: str):
        """Execute a query and return the results."""
        if not self.conn:
            # connect if not already connected
            self.connect()
        try:
            cursor = self.conn.cursor()
            cursor.execute(query)
            results = cursor.fetchall()
            cursor.close()
            return results
        except Exception as e:
            print("Error al ejecutar la consulta:", e)
            return []
        finally:
            if self.conn:
                # Close the connection if it was opened in this method
                self.conn.close()
    
    def store(self, data: List[Dict[str, Any]], table_name: str) -> None:
        try:

            cursor = self.conn.cursor()
            for item in data:
                # create a query from data where the keys are the column names and the values are the values to insert
                query_insert = f"INSERT INTO {table_name} ({', '.join(item.keys())}) VALUES ({', '.join(['%s'] * len(item))});"
                cursor.execute(query_insert, tuple(item.values()))
            self.conn.commit()
            cursor.close()  
        except psycopg2.Error as e:
            print("Error al almacenar los datos:", e)
            if self.conn:
                self.conn.rollback()
        except ValueError as ve:
            print("Error de validación:", ve)
        except Exception as e:
            print("Error inesperado al almacenar los datos:", e)
            if self.conn:
                self.conn.rollback()
        finally:
            if self.conn:
                self.conn.close()


    def delete(self, table_name: str, condition: str):
        """Elimina registros asociados a un proyecto específico."""
        try:
            if not self.conn:
                self.connect()

            # Execute a SQL delete statement
            cursor = self.conn.cursor()
            cursor.execute(f"DELETE FROM {table_name} WHERE {condition};")
            self.conn.commit()
            cursor.close()
            print("Registros eliminados correctamente.")
        except Exception as e:
            print("Error al eliminar los registros:", e)
        finally:
            if self.conn:
                self.conn.close()


if __name__ == "__main__":
    # Example usage
    db = PostgresDB(host="localhost", dbname="testdb", user="user", 
                    password="password", sslmode="disable", port=5432)
    db.connect()
    print(db.get_info())

    db.disconnect()