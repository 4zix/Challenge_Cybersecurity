# api/Dockerfile
# Usar una imagen base oficial y actualizada de Python 3.12, que es segura y mantenida
FROM python:3.12-slim

# Establecer el directorio de trabajo dentro del contenedor
WORKDIR /app

# Copiar el archivo de requerimientos primero para aprovechar el cache de Docker
COPY requirements.txt .

# Instalar las dependencias de Python
RUN pip install --no-cache-dir -r requirements.txt

# Copiar todo el código de la aplicación al directorio de trabajo
COPY . .

# Exponer el puerto en el que correrá la aplicación
EXPOSE 8000

# Comando para ejecutar la aplicación cuando el contenedor inicie
# El host 0.0.0.0 es crucial para que sea accesible desde fuera del contenedor
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]