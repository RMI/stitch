# Stitch Seed container

This package/deployment is intended to add fake data to a running stitch
instance, for demonstration and testing purposes

It also serves as a base/starting point of an ETL container, since this handles
model validation and POSTing Oil and Gas fields to the application.

It reads static seed JSON files from `data`, and also generates objects for
posting with `Faker`
