# CV Screening Platform

A Django-based platform that evaluates CVs against job prompts using AI.

## Features

- User authentication with JWT tokens
- CV PDF upload and evaluation
- AI-powered CV evaluation using OpenRouter
- Dual database setup (MySQL for auth, MongoDB for data)
- Async processing with Celery
- RESTful API with OpenAPI documentation

## Project Structure

```
cv-reader/
├── cv_screening/          # Django project settings
│   ├── settings.py       # Dual DB config, JWT, etc.
│   ├── routers.py        # Database routing for MySQL/MongoDB
│   └── urls.py           # Main URL configuration
├── app/                  # Main application
│   ├── models.py         # User (MySQL) and CV models (MongoDB)
│   ├── serializers.py    # DRF serializers
│   ├── views.py          # API views
│   ├── urls.py           # App URL routing
│   └── services/         # Business logic services
│       ├── ai_client.py      # AI evaluation client
│       ├── cv_parser.py      # PDF text extraction
│       ├── evaluation_service.py  # Orchestration service
│       └── file_security.py   # File validation
├── requirements.txt      # Python dependencies
└── manage.py            # Django management script
```

## Setup

1. Create virtual environment:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Environment configuration:
   ```bash
   # Copy the example environment file
   cp .env.example .env
   # Edit .env with your database credentials and API keys
   ```

4. AI Configuration:
   ```bash
   # Required: OpenRouter API key for AI evaluation
   OPENROUTER_API_KEY=sk-or-v1-your-openrouter-api-key-here
   ```

4. Run migrations:
   ```bash
   python manage.py migrate
   ```

5. Create superuser:
   ```bash
   python manage.py createsuperuser
   ```

6. Run development server:
   ```bash
   python manage.py runserver
   ```

## Running with Docker

### Prerequisites
- Docker and Docker Compose installed

### Quick Start
```bash
# Copy environment file
cp .env.example .env
# Edit .env with your settings if needed

# Start all services
docker-compose up --build

# The API will be available at http://localhost:8000
# API documentation at http://localhost:8000/api/schema/swagger-ui/
```

### Individual Services
```bash
# Start only the API
docker-compose up api

# Start only the Celery worker
docker-compose up celery-worker

# Start only MinIO
docker-compose up minio

# Start all services in background
docker-compose up -d

# View logs
docker-compose logs -f api
docker-compose logs -f celery-worker
docker-compose logs -f minio

# Stop all services
docker-compose down
```

### MinIO Console Access
When MinIO is running, you can access the web console at:
- **URL**: http://localhost:9001
- **Username**: minioadmin
- **Password**: minioadmin

This allows you to browse uploaded CV files and manage storage buckets.

### Development with Docker
```bash
# Rebuild after code changes
docker-compose up --build --force-recreate

# Run Django shell in container
docker-compose exec api python manage.py shell

# Run tests in container
docker-compose exec api python manage.py test
```

## API Endpoints

- `POST /api/auth/register/` - User registration
- `POST /api/auth/login/` - User login
- `POST /api/auth/token/refresh/` - Refresh JWT token
- `POST /api/cv-evaluations/` - Upload CV and create evaluation request
- `GET /api/cv-evaluations/` - List user's evaluation history
- `GET /api/cv-evaluations/{id}/` - Get evaluation details
- `GET /api/health/` - Health check endpoint

## Database Setup

- **MySQL**: User authentication and Django admin data
- **MongoDB**: CV uploads and evaluation requests
- **Redis**: Celery broker and result backend

Configure connection strings in `.env` file.

## Architecture

### Async Processing Flow
1. User uploads CV with job prompt
2. File is stored locally and metadata saved to MongoDB
3. Evaluation request created in MongoDB with status 'pending'
4. Celery task is enqueued for AI processing
5. User can poll the evaluation endpoint to check status
6. Once complete, AI results are stored and available via API

### Services
- **API Service**: Django REST API with JWT authentication
- **Celery Worker**: Background task processing for AI evaluation
- **Redis**: Message broker for Celery tasks
- **MySQL**: User data and Django internals
- **MongoDB**: CV data and evaluation results
- **MinIO**: S3-compatible object storage for CV files

### AI Integration

The platform uses **OpenRouter** for production AI-powered CV evaluation. The system is designed to work with multiple AI models through OpenRouter's unified API:

- **qwen/qwen3-coder:free** (default) - Fast, cost-effective coding model
- **anthropic/claude-3-haiku** - High-quality reasoning
- **openai/gpt-4** - Advanced language understanding
- **meta-llama/llama-3-70b-instruct** - Large language model

#### AI Evaluation Process

1. **Text Extraction**: PDF content is extracted using PDFMiner/PyMuPDF
2. **AI Analysis**: Extracted text is sent to OpenRouter with structured prompts
3. **Structured Response**: AI returns JSON with score, rationale, matches, and gaps
4. **Result Storage**: Evaluation results stored in MongoDB with status tracking

#### Configuration

The OpenRouter client automatically retrieves the API key from the `OPENROUTER_API_KEY` environment variable:

```bash
# Required environment variable
export OPENROUTER_API_KEY=sk-or-v1-your-api-key-here
```

The client can also be initialized with an explicit API key:

```python
from app.services.ai_client import OpenRouterClient

# Using environment variable (recommended)
client = OpenRouterClient()

# Using explicit API key
client = OpenRouterClient(api_key="sk-or-v1-your-key")
```

#### Circuit Breaker Protection

The AI client includes circuit breaker protection to handle:
- API timeouts and rate limits
- Service outages
- Invalid responses
- Automatic recovery when service is restored

## Production Deployment & Scaling

### Security Best Practices

#### Authentication & Authorization
- **JWT Token Rotation**: Implement refresh token rotation every 7 days
- **IP/Device Tracking**: Optional IP and device fingerprinting for security
- **Rate Limiting**: Implement rate limiting on API endpoints (100 requests/hour per user)
- **Token Blacklisting**: JWT tokens are automatically blacklisted on refresh

#### File Upload Security
- **File Type Validation**: Only PDF files accepted with MIME type checking
- **Size Limits**: Maximum 10MB file size limit
- **Virus Scanning**: Placeholder for ClamAV integration
- **Storage**: Files stored in secure media directory with hashed filenames

#### Data Protection
- **Encryption**: Use HTTPS/TLS 1.3 for all communications
- **Environment Variables**: Never commit secrets to version control
- **Database Security**: Use strong passwords and connection pooling

### Scaling Strategies

#### Horizontal Scaling
```bash
# Scale API instances
docker-compose up --scale api=3

# Scale Celery workers
docker-compose up --scale celery-worker=5
```

#### Load Balancing
- Use Nginx or AWS ALB for API load balancing
- Redis cluster for high availability
- MongoDB replica set for read scaling

#### Database Optimization
- **MySQL**: Connection pooling, read replicas for auth data
- **MongoDB**: Sharding for large CV collections, indexing on user_id and timestamps
- **Redis**: Persistence enabled for task queue reliability

#### Caching Strategy
- **API Responses**: Redis caching for evaluation history (TTL: 5 minutes)
- **File Metadata**: Cache frequently accessed CV metadata
- **Session Data**: Redis for session storage if needed

### Monitoring & Observability

#### Metrics Endpoints
- **Health Check**: `/api/health/` - Service availability monitoring
- **Prometheus Metrics**: `/metrics/` - Performance and business metrics

#### Key Metrics to Monitor
- Request latency and throughput
- CV evaluation success/failure rates
- Celery queue depth and processing times
- Database connection pools
- AI service circuit breaker status
- File upload success rates

#### Alerting Rules
- Circuit breaker open state
- High error rates (>5%)
- Queue depth > 100 pending tasks
- Database connection pool exhaustion
- AI service response time > 30 seconds

### Backup & Recovery

#### Database Backups
```bash
# MySQL backup
docker exec cv-screening-mysql mysqldump -u root -p cv_screening_auth > backup.sql

# MongoDB backup
docker exec cv-screening-mongodb mongodump --out /backup
```

#### File Storage
- Use S3-compatible storage for production file storage
- Implement cross-region replication for disaster recovery
- Set lifecycle policies for automatic cleanup

### Performance Optimization

#### Database Indexing
- MongoDB: Compound indexes on `(user_id, created_at)` for evaluation queries
- MySQL: Indexes on email and common query fields

#### API Optimization
- Pagination on all list endpoints (20 items per page)
- Selective field serialization for large responses
- Compression enabled for API responses

#### Celery Optimization
- **Prefetch**: Configure worker prefetch settings based on workload
- **Concurrency**: Adjust worker concurrency (default: CPU cores)
- **Routing**: Route different task types to specialized workers

### Testing Strategy

#### Running Tests
```bash
# Unit tests
pytest app/tests/test_serializers.py app/tests/test_services.py -v

# Integration tests
pytest app/tests/test_integration.py -v --tb=short

# All tests
pytest --cov=app --cov-report=html
```

#### Test Coverage Goals
- **Unit Tests**: 80%+ coverage for services and utilities
- **Integration Tests**: Full API flow testing
- **Load Tests**: Simulate concurrent uploads and evaluations

### Environment Configurations

#### Development
```bash
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
# Minimal logging, full debug features
```

#### Staging
```bash
DEBUG=False
ALLOWED_HOSTS=staging.example.com
# Production-like settings with debug logging
```

#### Production
```bash
DEBUG=False
ALLOWED_HOSTS=api.example.com
# Full security, minimal logging, monitoring enabled
SECURE_SSL_REDIRECT=True
SESSION_COOKIE_SECURE=True
```

### Troubleshooting

#### Common Issues
- **Celery Connection Issues**: Check Redis connectivity and broker URL
- **MongoDB Connection Timeout**: Verify connection string and authentication
- **File Upload Failures**: Check media directory permissions and disk space
- **Circuit Breaker Open**: Indicates AI service issues, check API keys and quotas

#### Debug Commands
```bash
# Check Celery worker status
docker-compose exec celery-worker celery -A cv_screening inspect active

# Monitor Redis queue
docker-compose exec redis redis-cli LLEN cv_screening

# Check MongoDB connections
docker-compose exec mongodb mongo --eval "db.serverStatus().connections"
```
