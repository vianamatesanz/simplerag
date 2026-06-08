import psycopg2
from psycopg2.extras import RealDictCursor
import logging

def read_sql_table(
    table,
    fields,
    joins=None,
    where=None,
    db_config=None
):
    """
    Función genérica para hacer consultas a PostgreSQL con joins y filtros.

    :param table: Tabla principal (string)
    :param fields: Lista de campos a seleccionar
    :param joins: Lista de diccionarios con joins. Cada join debe tener:
        {
            "type": "INNER JOIN" | "LEFT JOIN",
            "table": "nombre_tabla",
            "on": "condición_join"
        }
    :param where: Diccionario {campo: valor} para el WHERE
    :param db_config: Diccionario con los datos de conexión
    :return: Lista de registros como diccionarios
    """

    if db_config is None:
        # Puedes parametrizar esto o cargar de un config
        logging.error('DB config is None, please provide the SQL connection credentials.')
        return

    # Construir SELECT
    fields_str = ", ".join(fields)

    query = f"SELECT {fields_str} FROM {table}"

    # Añadir JOINS
    if joins:
        for join in joins:
            query += f" {join['type']} {join['table']} ON {join['on']}"

    # Añadir WHERE
    params = []
    if where:
        where_clauses = []
        for idx, (k, v) in enumerate(where.items()):
            if isinstance(v, list):
                placeholders = ", ".join(["%s"] * len(v))
                where_clauses.append(f"{k} IN ({placeholders})")
                params.extend(v)
            else:
                where_clauses.append(f"{k} = %s")
                params.append(v)
        query += " WHERE " + " AND ".join(where_clauses)

    # Conexión y ejecución
    conn = psycopg2.connect(**db_config)
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, params)
            results = cur.fetchall()
    finally:
        conn.close()

    return results


### Calling example

# resultados = read_sql_table(
#     table="projects",
#     fields=[
#         "projects.id_project",
#         "config.config_json"
#     ],
#     joins=[
#         {
#             "type": "INNER JOIN",
#             "table": "config",
#             "on": "projects.id_config = config.id_config"
#         }
#     ],
#     where={
#         "projects.id_project": 123
#     },
#     db_config={
#         "host": "localhost",
#         "database": "mi_base",
#         "user": "mi_usuario",
#         "password": "mi_password",
#         "port": 5432
#     }
# )