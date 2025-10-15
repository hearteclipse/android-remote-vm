.PHONY: help build up down restart logs clean install test

help:
	@echo "VMI Platform - Available commands:"
	@echo "  make build      - Build all Docker images"
	@echo "  make up         - Start all services"
	@echo "  make down       - Stop all services"
	@echo "  make restart    - Restart all services"
	@echo "  make logs       - View logs from all services"
	@echo "  make clean      - Remove all containers, volumes, and images"
	@echo "  make install    - Install dependencies locally"
	@echo "  make test       - Run tests"

build:
	docker-compose build

up:
	docker-compose up -d
	docker exec -it vmi-backend pip install aiortc av
	docker-compose restart backend
	@echo "Services started!"
	@echo "Web Client: http://localhost:8080"
	@echo "API Docs: http://localhost:8000/docs"
	@echo "Admin Dashboard: http://localhost:8080/admin"

down:
	docker-compose down

restart:
	docker-compose restart

logs:
	docker-compose logs -f

clean:
	docker-compose down -v --rmi all
	@echo "Cleaned up all containers, volumes, and images"

install:
	cd backend && pip install -r requirements.txt

test:
	cd backend && pytest tests/

# GCP deployment commands
gcp-auth:
	gcloud auth login
	gcloud config set project $(GCP_PROJECT_ID)

gcp-build:
	gcloud builds submit --config cloudbuild.yaml

gcp-deploy:
	gcloud run deploy vmi-backend \
		--image gcr.io/$(GCP_PROJECT_ID)/vmi-backend \
		--platform managed \
		--region $(GCP_REGION) \
		--allow-unauthenticated

# Development helpers
dev-backend:
	cd backend && uvicorn main:app --reload --host 0.0.0.0 --port 8000

dev-db:
	docker-compose up -d postgres redis

