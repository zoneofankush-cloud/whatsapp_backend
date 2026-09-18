# Python ka lightweight base image
FROM python:3.14.7-slim-trixie

# Container ke andar working directory set kar rahe hain
WORKDIR /app

# Requirements file ko container me copy karna (Ye zaroori hai!)
COPY requirements.txt ./

# Dependencies ke sath gunicorn aur uvicorn dono install karna
RUN pip install --no-cache-dir -r requirements.txt gunicorn uvicorn

# Copy all necessary backend code and modules
COPY apps/ ./apps/
COPY repository/ ./repository/
COPY services/ ./services/
COPY utils/ ./utils/
COPY main.py ./

# Expose port and run
EXPOSE 8000
CMD ["gunicorn", "main:app", "-w", "4", "-k", "uvicorn.workers.UvicornWorker", "-b", "0.0.0.0:8000"]