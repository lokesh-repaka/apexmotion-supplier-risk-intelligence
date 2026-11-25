# ==============================================================================
# ApexMotion Terraform Input Variables
# Reference: TASKS.md (P16-3), CLAUDE.md Sec 6, and HLD Sec 6 & 7
# ==============================================================================

variable "environment" {
  type        = string
  description = "Target deployment environment (production, staging, dev)"
  default     = "production"
}

variable "aws_region" {
  type        = string
  description = "AWS region for deployment (e.g. eu-central-1 or ap-south-1)"
  default     = "eu-central-1"
}

variable "vpc_cidr" {
  type        = string
  description = "VPC CIDR block for network isolation"
  default     = "10.100.0.0/16"
}

variable "eks_cluster_name" {
  type        = string
  description = "Name identifier for the Amazon EKS cluster"
  default     = "apexmotion-eks"
}

variable "aurora_min_capacity" {
  type        = number
  description = "Minimum ACU capacity for Aurora PostgreSQL Serverless v2"
  default     = 0.5
}

variable "aurora_max_capacity" {
  type        = number
  description = "Maximum ACU capacity for Aurora PostgreSQL Serverless v2"
  default     = 32.0
}

variable "audit_retention_years" {
  type        = number
  description = "Retention period in years for S3 WORM Compliance mode"
  default     = 7
}
