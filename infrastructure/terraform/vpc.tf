# ==============================================================================
# ApexMotion Network Architecture & VPC Topology (Slide 20 Pattern)
# Reference: HLD Sec 6.1 (10.100.0.0/16 across 3 AZs with 3 network tiers)
# ==============================================================================

locals {
  azs = slice(data.aws_availability_zones.available.names, 0, 3)

  public_subnets = [
    "10.100.1.0/24",
    "10.100.2.0/24",
    "10.100.3.0/24",
  ]

  application_subnets = [
    "10.100.10.0/24",
    "10.100.20.0/24",
    "10.100.30.0/24",
  ]

  data_subnets = [
    "10.100.100.0/24",
    "10.100.200.0/24",
    "10.100.210.0/24",
  ]
}

# ------------------------------------------------------------------------------
# 1. Virtual Private Cloud (VPC)
# ------------------------------------------------------------------------------

resource "aws_vpc" "main" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {
    Name                                                               = "apexmotion-${var.environment}-vpc"
    "kubernetes.io/cluster/${var.eks_cluster_name}-${var.environment}" = "shared"
  }
}

# ------------------------------------------------------------------------------
# 2. Public DMZ Subnets (ALB, WAF, NAT Gateways)
# ------------------------------------------------------------------------------

resource "aws_subnet" "public" {
  count                   = 3
  vpc_id                  = aws_vpc.main.id
  cidr_block              = local.public_subnets[count.index]
  availability_zone       = local.azs[count.index]
  map_public_ip_on_launch = true

  tags = {
    Name                                                               = "apexmotion-${var.environment}-public-${local.azs[count.index]}"
    Tier                                                               = "Public-DMZ"
    "kubernetes.io/role/elb"                                           = "1"
    "kubernetes.io/cluster/${var.eks_cluster_name}-${var.environment}" = "shared"
  }
}

resource "aws_internet_gateway" "gw" {
  vpc_id = aws_vpc.main.id

  tags = {
    Name = "apexmotion-${var.environment}-igw"
  }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.gw.id
  }

  tags = {
    Name = "apexmotion-${var.environment}-public-rt"
  }
}

resource "aws_route_table_association" "public" {
  count          = 3
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

# ------------------------------------------------------------------------------
# 3. NAT Gateways (Multi-AZ Egress for Application Tier)
# ------------------------------------------------------------------------------

resource "aws_eip" "nat" {
  count  = 3
  domain = "vpc"

  tags = {
    Name = "apexmotion-${var.environment}-nat-eip-${local.azs[count.index]}"
  }
}

resource "aws_nat_gateway" "nat" {
  count         = 3
  allocation_id = aws_eip.nat[count.index].id
  subnet_id     = aws_subnet.public[count.index].id

  tags = {
    Name = "apexmotion-${var.environment}-nat-${local.azs[count.index]}"
  }

  depends_on = [aws_internet_gateway.gw]
}

# ------------------------------------------------------------------------------
# 4. Private Application Subnets (EKS Pods, Envoy, LiteLLM)
# ------------------------------------------------------------------------------

resource "aws_subnet" "application" {
  count             = 3
  vpc_id            = aws_vpc.main.id
  cidr_block        = local.application_subnets[count.index]
  availability_zone = local.azs[count.index]

  tags = {
    Name                                                               = "apexmotion-${var.environment}-app-${local.azs[count.index]}"
    Tier                                                               = "Private-Application"
    "kubernetes.io/role/internal-elb"                                  = "1"
    "kubernetes.io/cluster/${var.eks_cluster_name}-${var.environment}" = "shared"
    "karpenter.sh/discovery"                                           = "apexmotion-${var.environment}"
  }
}

resource "aws_route_table" "application" {
  count  = 3
  vpc_id = aws_vpc.main.id

  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.nat[count.index].id
  }

  tags = {
    Name = "apexmotion-${var.environment}-app-rt-${local.azs[count.index]}"
  }
}

resource "aws_route_table_association" "application" {
  count          = 3
  subnet_id      = aws_subnet.application[count.index].id
  route_table_id = aws_route_table.application[count.index].id
}

# ------------------------------------------------------------------------------
# 5. Private Data Subnets (Isolated Tier: Aurora, Neptune, MSK, OpenSearch, Redis)
# Zero Internet Egress per HLD Sec 6.1
# ------------------------------------------------------------------------------

resource "aws_subnet" "data" {
  count             = 3
  vpc_id            = aws_vpc.main.id
  cidr_block        = local.data_subnets[count.index]
  availability_zone = local.azs[count.index]

  tags = {
    Name = "apexmotion-${var.environment}-data-${local.azs[count.index]}"
    Tier = "Private-Data-Isolated"
  }
}

resource "aws_route_table" "data" {
  vpc_id = aws_vpc.main.id

  tags = {
    Name = "apexmotion-${var.environment}-data-rt"
  }
}

resource "aws_route_table_association" "data" {
  count          = 3
  subnet_id      = aws_subnet.data[count.index].id
  route_table_id = aws_route_table.data.id
}

# S3 VPC Gateway Endpoint (Zero egress to public S3 endpoints)
resource "aws_vpc_endpoint" "s3" {
  vpc_id          = aws_vpc.main.id
  service_name    = "com.amazonaws.${var.aws_region}.s3"
  route_table_ids = concat(aws_route_table.application[*].id, [aws_route_table.data.id])

  tags = {
    Name = "apexmotion-${var.environment}-s3-endpoint"
  }
}

# ------------------------------------------------------------------------------
# 6. Security Groups
# ------------------------------------------------------------------------------

# EKS Control Plane Security Group
resource "aws_security_group" "eks_cluster_sg" {
  name        = "apexmotion-${var.environment}-eks-cluster-sg"
  description = "Security group for EKS control plane communicating with worker nodes"
  vpc_id      = aws_vpc.main.id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "apexmotion-${var.environment}-eks-cluster-sg"
  }
}

# EKS Worker Nodes Security Group
resource "aws_security_group" "eks_nodes_sg" {
  name        = "apexmotion-${var.environment}-eks-nodes-sg"
  description = "Security group for EKS worker nodes and pod workloads"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port       = 0
    to_port         = 0
    protocol        = "-1"
    security_groups = [aws_security_group.eks_cluster_sg.id]
  }

  ingress {
    from_port = 0
    to_port   = 0
    protocol  = "-1"
    self      = true
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name                                                               = "apexmotion-${var.environment}-eks-nodes-sg"
    "kubernetes.io/cluster/${var.eks_cluster_name}-${var.environment}" = "owned"
  }
}

# Aurora PostgreSQL Security Group (Port 5432)
resource "aws_security_group" "aurora_sg" {
  name        = "apexmotion-${var.environment}-aurora-sg"
  description = "Security group for Aurora PostgreSQL 16 cluster"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "PostgreSQL from EKS worker nodes"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.eks_nodes_sg.id]
  }

  tags = {
    Name = "apexmotion-${var.environment}-aurora-sg"
  }
}

# Amazon Neptune Graph Security Group (Port 8182)
resource "aws_security_group" "neptune_sg" {
  name        = "apexmotion-${var.environment}-neptune-sg"
  description = "Security group for Amazon Neptune OpenCypher cluster"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "OpenCypher graph queries from EKS worker nodes"
    from_port       = 8182
    to_port         = 8182
    protocol        = "tcp"
    security_groups = [aws_security_group.eks_nodes_sg.id]
  }

  tags = {
    Name = "apexmotion-${var.environment}-neptune-sg"
  }
}

# Amazon MSK Kafka Security Group (Ports 9092, 9094, 9098)
resource "aws_security_group" "msk_sg" {
  name        = "apexmotion-${var.environment}-msk-sg"
  description = "Security group for Amazon MSK Kafka cluster"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "Plaintext Kafka port (dev/mock)"
    from_port       = 9092
    to_port         = 9092
    protocol        = "tcp"
    security_groups = [aws_security_group.eks_nodes_sg.id]
  }

  ingress {
    description     = "TLS Kafka broker communication"
    from_port       = 9094
    to_port         = 9094
    protocol        = "tcp"
    security_groups = [aws_security_group.eks_nodes_sg.id]
  }

  ingress {
    description     = "IAM Auth TLS Kafka broker communication"
    from_port       = 9098
    to_port         = 9098
    protocol        = "tcp"
    security_groups = [aws_security_group.eks_nodes_sg.id]
  }

  tags = {
    Name = "apexmotion-${var.environment}-msk-sg"
  }
}

# Amazon OpenSearch Security Group (Port 443)
resource "aws_security_group" "opensearch_sg" {
  name        = "apexmotion-${var.environment}-opensearch-sg"
  description = "Security group for Amazon OpenSearch vector search domain"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "HTTPS vector search queries from EKS worker nodes"
    from_port       = 443
    to_port         = 443
    protocol        = "tcp"
    security_groups = [aws_security_group.eks_nodes_sg.id]
  }

  tags = {
    Name = "apexmotion-${var.environment}-opensearch-sg"
  }
}

# Amazon ElastiCache Redis Security Group (Port 6379)
resource "aws_security_group" "redis_sg" {
  name        = "apexmotion-${var.environment}-redis-sg"
  description = "Security group for ElastiCache Redis cluster"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "Redis port from EKS worker nodes"
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = [aws_security_group.eks_nodes_sg.id]
  }

  tags = {
    Name = "apexmotion-${var.environment}-redis-sg"
  }
}
