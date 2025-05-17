# Use official Python slim image as base
FROM python:3.10-slim

# Set working directory inside container
WORKDIR /app

# Copy only requirements file first (to leverage Docker cache)
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the backend code into the container
COPY backend ./backend

# Command to run your FastAPI app using uvicorn on port 8000
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
