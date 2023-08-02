# GitHub Report

GitHub Report tool.

* Free software: BSD 3 Clause
* Documentation: https://opensciencelabs.github.io/ghreport


## Configuration file

In order to create a configuration file, add to your project, at
the root level, a file called .ghreport.yaml, with the following
structure:

```yaml
name: myproject-name-slug
title: "My Report Title"
env-file: .env
repos:
  - myorg-1/myproject1
authors:
  - gh-username-1: GitHub Username 1
output-dir: "/tmp/ghreport"
```
