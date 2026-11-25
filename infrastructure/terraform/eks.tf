# ==============================================================================
# ApexMotion Amazon EKS Cluster (Kubernetes 1.30)
# Reference: CLAUDE.md Sec 6 (K8s 1.30, KEDA autoscaling, GPU vLLM nodes)
# ==============================================================================

# ------------------------------------------------------------------------------
# 1. EKS IAM Roles
# ------------------------------------------------------------------------------

resource "aws_iam_role" "eks_cluster_role" {
  name = "apexmotion-${var.environment}-eks-cluster-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "eks.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "eks_cluster_policy" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSClusterPolicy"
  role       = aws_iam_role.eks_cluster_role.name
}

resource "aws_iam_role_policy_attachment" "eks_vpc_resource_controller" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSVPCResourceController"
  role       = aws_iam_role.eks_cluster_role.name
}

resource "aws_iam_role" "eks_node_role" {
  name = "apexmotion-${var.environment}-eks-node-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ec2.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "eks_worker_node_policy" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSWorkerNodePolicy"
  role       = aws_iam_role.eks_node_role.name
}

resource "aws_iam_role_policy_attachment" "eks_cni_policy" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy"
  role       = aws_iam_role.eks_node_role.name
}

resource "aws_iam_role_policy_attachment" "eks_container_registry_ro" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
  role       = aws_iam_role.eks_node_role.name
}

# ------------------------------------------------------------------------------
# 2. Amazon EKS 1.30 Cluster Control Plane
# ------------------------------------------------------------------------------

resource "aws_eks_cluster" "main" {
  name     = "${var.eks_cluster_name}-${var.environment}"
  role_arn = aws_iam_role.eks_cluster_role.arn
  version  = "1.30"

  vpc_config {
    subnet_ids              = aws_subnet.application[*].id
    security_group_ids      = [aws_security_group.eks_cluster_sg.id]
    endpoint_private_access = true
    endpoint_public_access  = true
  }

  enabled_cluster_log_types = ["api", "audit", "authenticator", "controllerManager", "scheduler"]

  depends_on = [
    aws_iam_role_policy_attachment.eks_cluster_policy,
    aws_iam_role_policy_attachment.eks_vpc_resource_controller,
  ]

  tags = {
    Name = "${var.eks_cluster_name}-${var.environment}"
  }
}

# ------------------------------------------------------------------------------
# 3. OIDC Identity Provider for IAM Roles for Service Accounts (IRSA)
# ------------------------------------------------------------------------------

data "tls_certificate" "eks" {
  url = aws_eks_cluster.main.identity[0].oidc[0].issuer
}

resource "aws_iam_openid_connect_provider" "eks" {
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = [data.tls_certificate.eks.certificates[0].sha1_fingerprint]
  url             = aws_eks_cluster.main.identity[0].oidc[0].issuer
}

# ------------------------------------------------------------------------------
# 4. General Application Node Group (FastAPI, LangGraph Agents, Worker Pods)
# ------------------------------------------------------------------------------

resource "aws_eks_node_group" "application" {
  cluster_name    = aws_eks_cluster.main.name
  node_group_name = "apexmotion-${var.environment}-app-nodes"
  node_role_arn   = aws_iam_role.eks_node_role.arn
  subnet_ids      = aws_subnet.application[*].id

  instance_types = ["m6i.xlarge", "m6i.2xlarge"]
  capacity_type  = "ON_DEMAND"

  scaling_config {
    desired_size = 3
    max_size     = 10
    min_size     = 3
  }

  update_config {
    max_unavailable = 1
  }

  labels = {
    role        = "application"
    environment = var.environment
  }

  depends_on = [
    aws_iam_role_policy_attachment.eks_worker_node_policy,
    aws_iam_role_policy_attachment.eks_cni_policy,
    aws_iam_role_policy_attachment.eks_container_registry_ro,
  ]

  tags = {
    Name = "apexmotion-${var.environment}-app-nodes"
  }
}

# ------------------------------------------------------------------------------
# 5. Dedicated GPU Node Group for Self-Hosted vLLM (Confidential Contracts)
# ------------------------------------------------------------------------------

resource "aws_eks_node_group" "gpu_vllm" {
  cluster_name    = aws_eks_cluster.main.name
  node_group_name = "apexmotion-${var.environment}-gpu-vllm-nodes"
  node_role_arn   = aws_iam_role.eks_node_role.arn
  subnet_ids      = aws_subnet.application[*].id

  instance_types = ["g6e.12xlarge"]
  capacity_type  = "ON_DEMAND"

  scaling_config {
    desired_size = 1
    max_size     = 2
    min_size     = 0
  }

  taint {
    key    = "dedicated"
    value  = "vllm"
    effect = "NO_SCHEDULE"
  }

  labels = {
    workload    = "confidential-vllm"
    environment = var.environment
  }

  depends_on = [
    aws_iam_role_policy_attachment.eks_worker_node_policy,
    aws_iam_role_policy_attachment.eks_cni_policy,
    aws_iam_role_policy_attachment.eks_container_registry_ro,
  ]

  tags = {
    Name = "apexmotion-${var.environment}-gpu-vllm-nodes"
  }
}
