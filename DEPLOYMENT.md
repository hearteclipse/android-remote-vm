# 🚀 Deployment Guide - VMI Platform

Complete deployment guide for the Virtual Mobile Infrastructure platform.

## Table of Contents

- [Local Deployment](#local-deployment)
- [GCP Deployment](#gcp-deployment)
- [AWS Deployment](#aws-deployment)
- [Azure Deployment](#azure-deployment)
- [Production Checklist](#production-checklist)

---

## Local Deployment

### Using Docker Compose (Recommended)

```bash
# 1. Clone repository
git clone https://github.com/yourusername/android-remote-vm.git
cd android-remote-vm

# 2. Configure environment
cp .env.example .env
nano .env  # Edit configuration

# 3. Build images
docker-compose build

# 4. Start services
docker-compose up -d

# 5. Check status
docker-compose ps

# 6. View logs
docker-compose logs -f
```

### Using Makefile

```bash
# Build and start
make build
make up

# View logs
make logs

# Stop services
make down

# Clean up everything
make clean
```

---

## GCP Deployment

### Option 1: Compute Engine VM (Recommended)

**Best for**: Full control, KVM support, multiple devices

#### Step 1: Create VM Instance

```bash
# Set variables
export PROJECT_ID="your-gcp-project-id"
export REGION="us-central1"
export ZONE="${REGION}-a"
export INSTANCE_NAME="vmi-host-1"

# Create VM with nested virtualization
gcloud compute instances create $INSTANCE_NAME \
  --project=$PROJECT_ID \
  --zone=$ZONE \
  --machine-type=n2-standard-8 \
  --image-family=debian-12 \
  --image-project=debian-cloud \
  --boot-disk-size=100GB \
  --boot-disk-type=pd-ssd \
  --enable-nested-virtualization \
  --tags=vmi-host,http-server,https-server \
  --metadata=startup-script='#!/bin/bash
    apt-get update
    apt-get install -y docker.io docker-compose git make
    usermod -aG docker $(whoami)
    systemctl enable docker
    systemctl start docker
  '
```

#### Step 2: Configure Firewall

```bash
# Allow HTTP/HTTPS
gcloud compute firewall-rules create allow-vmi-web \
  --project=$PROJECT_ID \
  --allow=tcp:80,tcp:443,tcp:8000,tcp:8080 \
  --target-tags=vmi-host

# Allow WebRTC ports
gcloud compute firewall-rules create allow-vmi-webrtc \
  --project=$PROJECT_ID \
  --allow=tcp:50000-51000,udp:50000-51000 \
  --target-tags=vmi-host
```

#### Step 3: Deploy Application

```bash
# SSH into instance
gcloud compute ssh $INSTANCE_NAME --zone=$ZONE

# Clone and setup
git clone https://github.com/yourusername/android-remote-vm.git
cd android-remote-vm
cp .env.example .env

# Edit .env with production settings
nano .env

# Build and start
make build
make up
```

#### Step 4: Setup Cloud SQL (Production)

```bash
# Create Cloud SQL instance
gcloud sql instances create vmi-postgres \
  --project=$PROJECT_ID \
  --database-version=POSTGRES_15 \
  --tier=db-g1-small \
  --region=$REGION \
  --storage-type=SSD \
  --storage-size=10GB \
  --backup-start-time=03:00 \
  --enable-bin-log

# Create database
gcloud sql databases create vmi_db \
  --instance=vmi-postgres

# Create user
gcloud sql users create vmi_user \
  --instance=vmi-postgres \
  --password=STRONG_PASSWORD_HERE

# Get connection name
gcloud sql instances describe vmi-postgres \
  --format='value(connectionName)'

# Update .env with Cloud SQL connection
# DATABASE_URL=postgresql://vmi_user:password@/vmi_db?host=/cloudsql/CONNECTION_NAME
```

#### Step 5: Setup Cloud Memorystore (Redis)

```bash
# Create Redis instance
gcloud redis instances create vmi-redis \
  --project=$PROJECT_ID \
  --region=$REGION \
  --tier=basic \
  --size=1 \
  --redis-version=redis_7_0

# Get Redis host
gcloud redis instances describe vmi-redis \
  --region=$REGION \
  --format='value(host)'

# Update .env
# REDIS_URL=redis://REDIS_HOST:6379
```

### Option 2: Cloud Run (Serverless)

**Best for**: Backend API only (Android containers need VMs)

```bash
# Build and push backend
gcloud builds submit \
  --project=$PROJECT_ID \
  --tag=gcr.io/$PROJECT_ID/vmi-backend \
  backend/

# Deploy to Cloud Run
gcloud run deploy vmi-backend \
  --project=$PROJECT_ID \
  --image=gcr.io/$PROJECT_ID/vmi-backend \
  --platform=managed \
  --region=$REGION \
  --allow-unauthenticated \
  --memory=2Gi \
  --cpu=2 \
  --max-instances=10 \
  --set-env-vars="DATABASE_URL=postgresql://..." \
  --set-env-vars="REDIS_URL=redis://..."
```

### Option 3: GKE (Kubernetes)

**Best for**: Large scale, auto-scaling

```bash
# Create GKE cluster
gcloud container clusters create vmi-cluster \
  --project=$PROJECT_ID \
  --zone=$ZONE \
  --machine-type=n2-standard-8 \
  --num-nodes=3 \
  --enable-autoscaling \
  --min-nodes=1 \
  --max-nodes=10

# Deploy application
kubectl apply -f k8s/
```

---

## AWS Deployment

### Using EC2

#### Step 1: Launch EC2 Instance

```bash
# Launch instance with nested virtualization
aws ec2 run-instances \
  --image-id ami-0c55b159cbfafe1f0 \
  --instance-type m5.2xlarge \
  --key-name your-key-pair \
  --security-group-ids sg-xxxxxxxx \
  --subnet-id subnet-xxxxxxxx \
  --block-device-mappings DeviceName=/dev/xvda,Ebs={VolumeSize=100} \
  --cpu-options CoreCount=4,ThreadsPerCore=2
```

#### Step 2: Configure Security Group

```bash
# Allow HTTP/HTTPS
aws ec2 authorize-security-group-ingress \
  --group-id sg-xxxxxxxx \
  --protocol tcp \
  --port 80 \
  --cidr 0.0.0.0/0

aws ec2 authorize-security-group-ingress \
  --group-id sg-xxxxxxxx \
  --protocol tcp \
  --port 443 \
  --cidr 0.0.0.0/0

# Allow WebRTC
aws ec2 authorize-security-group-ingress \
  --group-id sg-xxxxxxxx \
  --protocol tcp \
  --port 50000-51000 \
  --cidr 0.0.0.0/0
```

#### Step 3: Setup RDS PostgreSQL

```bash
# Create RDS instance
aws rds create-db-instance \
  --db-instance-identifier vmi-postgres \
  --db-instance-class db.t3.medium \
  --engine postgres \
  --engine-version 15.3 \
  --master-username vmi_user \
  --master-user-password STRONG_PASSWORD \
  --allocated-storage 20 \
  --storage-type gp2
```

#### Step 4: Setup ElastiCache Redis

```bash
# Create Redis cluster
aws elasticache create-cache-cluster \
  --cache-cluster-id vmi-redis \
  --cache-node-type cache.t3.medium \
  --engine redis \
  --num-cache-nodes 1
```

---

## Azure Deployment

### Using Virtual Machines

#### Step 1: Create VM

```bash
# Create resource group
az group create \
  --name vmi-rg \
  --location eastus

# Create VM
az vm create \
  --resource-group vmi-rg \
  --name vmi-host-1 \
  --image UbuntuLTS \
  --size Standard_D8s_v3 \
  --admin-username azureuser \
  --generate-ssh-keys \
  --os-disk-size-gb 100
```

#### Step 2: Configure Network

```bash
# Open ports
az vm open-port \
  --resource-group vmi-rg \
  --name vmi-host-1 \
  --port 80 \
  --priority 1001

az vm open-port \
  --resource-group vmi-rg \
  --name vmi-host-1 \
  --port 443 \
  --priority 1002

az vm open-port \
  --resource-group vmi-rg \
  --name vmi-host-1 \
  --port 50000-51000 \
  --priority 1003
```

#### Step 3: Setup Azure Database for PostgreSQL

```bash
# Create PostgreSQL server
az postgres server create \
  --resource-group vmi-rg \
  --name vmi-postgres \
  --location eastus \
  --admin-user vmi_user \
  --admin-password STRONG_PASSWORD \
  --sku-name B_Gen5_1 \
  --version 15
```

---

## Production Checklist

### Security

- [ ] Change all default passwords
- [ ] Enable HTTPS with valid SSL certificate
- [ ] Implement proper authentication (JWT, OAuth2)
- [ ] Enable firewall rules
- [ ] Use managed database services
- [ ] Enable database encryption at rest
- [ ] Implement rate limiting
- [ ] Regular security updates
- [ ] Enable audit logging
- [ ] Use secrets management (GCP Secret Manager, AWS Secrets Manager)

### Performance

- [ ] Enable KVM for hardware acceleration
- [ ] Configure proper resource limits
- [ ] Setup CDN for static assets
- [ ] Implement caching strategy
- [ ] Database connection pooling
- [ ] Setup monitoring and alerting
- [ ] Configure autoscaling
- [ ] Optimize Docker images

### Reliability

- [ ] Setup automated backups
- [ ] Implement health checks
- [ ] Configure auto-restart policies
- [ ] Setup load balancing
- [ ] Implement graceful shutdown
- [ ] Setup disaster recovery plan
- [ ] Configure log aggregation
- [ ] Setup uptime monitoring

### Scalability

- [ ] Horizontal scaling strategy
- [ ] Database read replicas
- [ ] Redis cluster mode
- [ ] Container orchestration (Kubernetes)
- [ ] Resource monitoring
- [ ] Capacity planning
- [ ] Load testing

### Monitoring

```bash
# Install monitoring tools
docker-compose -f docker-compose.monitoring.yml up -d

# Services:
# - Prometheus: Metrics collection
# - Grafana: Visualization
# - Loki: Log aggregation
# - AlertManager: Alerting
```

### Backup Strategy

```bash
# Database backup script
#!/bin/bash
DATE=$(date +%Y%m%d_%H%M%S)
pg_dump $DATABASE_URL > backups/vmi_db_$DATE.sql
aws s3 cp backups/vmi_db_$DATE.sql s3://your-backup-bucket/

# Schedule with cron
0 2 * * * /path/to/backup.sh
```

---

## SSL/TLS Setup

### Using Let's Encrypt (Certbot)

```bash
# Install Certbot
sudo apt-get install certbot python3-certbot-nginx

# Get certificate
sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com

# Auto-renewal
sudo certbot renew --dry-run
```

### Update nginx configuration

```nginx
server {
    listen 443 ssl http2;
    server_name yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;
    
    # ... rest of configuration
}
```

---

## Monitoring and Logging

### Setup Prometheus + Grafana

```yaml
# docker-compose.monitoring.yml
version: '3.8'

services:
  prometheus:
    image: prom/prometheus
    volumes:
      - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml
    ports:
      - "9090:9090"

  grafana:
    image: grafana/grafana
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
```

### Cloud Monitoring

**GCP:**
```bash
# Enable monitoring
gcloud services enable monitoring.googleapis.com
gcloud services enable logging.googleapis.com
```

**AWS:**
```bash
# Enable CloudWatch
aws cloudwatch put-metric-alarm ...
```

---

## Troubleshooting

### Common Issues

1. **Containers won't start**: Check Docker logs
2. **Database connection errors**: Verify connection string
3. **WebRTC not working**: Check firewall rules
4. **Out of memory**: Increase instance size
5. **Slow performance**: Enable KVM

### Support Resources

- GitHub Issues
- Documentation
- Community Forum
- Email Support

---

**Questions?** Open an issue on GitHub or consult the main README.md

