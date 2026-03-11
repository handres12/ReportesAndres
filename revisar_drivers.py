import pyodbc

def mostrar_drivers():
    drivers = pyodbc.drivers()
    if not drivers:
        print("No se encontraron drivers ODBC instalados.")
    else:
        print("💡 Drivers ODBC instalados en tu equipo:")
        for driver in drivers:
            print(f"- {driver}")

if __name__ == "__main__":
    mostrar_drivers()