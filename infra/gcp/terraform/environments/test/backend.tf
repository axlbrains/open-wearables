terraform {
  backend "gcs" {
    prefix = "envs/test/ow-terraform-state"
    bucket = "axl-platform-tfstate-602690ff"
  }
}
