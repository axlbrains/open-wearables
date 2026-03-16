terraform {
  backend "gcs" {
    prefix = "envs/prod/ow-terraform-state"
    bucket = "axl-platform-tfstate-602690ff"
  }
}
