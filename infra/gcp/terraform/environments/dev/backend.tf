terraform {
  backend "gcs" {
    prefix = "envs/dev/ow-terraform-state"
    bucket = "axl-platform-tfstate-602690ff"
  }
}
