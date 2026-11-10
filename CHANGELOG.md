# 🪵 Changelog

## [0.0.6](https://github.com/elixir-europe-training/ELIXIR-TrP-KG-training-metadata/compare/v0.0.5..v0.0.6) - 2026-11-10

### 🐛 Bug Fixes

- Fix and rename harvesting workflow to make it run once every month (1st day of the month), update readme with instructions to download harvested data, change order of authors in paper.md to permute Vincent and Dimitris - ([53c8556](https://github.com/elixir-europe-training/ELIXIR-TrP-KG-training-metadata/commit/53c85563716a969f892136e3be5c1fdd95f32de9))
- Fixes left-over closing brackets - ([826215b](https://github.com/elixir-europe-training/ELIXIR-TrP-KG-training-metadata/commit/826215b426cc7f37aadbb7db415f7dcaa93862dd))

## [0.0.5](https://github.com/elixir-europe-training/ELIXIR-TrP-KG-training-metadata/compare/v0.0.4..v0.0.5) - 2025-11-20

### 📚 Documentation

- Add mermaid diagrams for architecture and workflow - ([98e0693](https://github.com/elixir-europe-training/ELIXIR-TrP-KG-training-metadata/commit/98e0693a79b8a75b0f6b1493a3f301f625a38d4a))

### 🛠️ Miscellaneous Tasks

- Update training data and bump version - ([87562df](https://github.com/elixir-europe-training/ELIXIR-TrP-KG-training-metadata/commit/87562dfa700ce170ef978cdb4c8ea694b18a39c9))

## [0.0.4](https://github.com/elixir-europe-training/ELIXIR-TrP-KG-training-metadata/compare/v0.0.4-beta..v0.0.4) - 2025-11-13

### 🛠️ Miscellaneous Tasks

- Update training data and bump version - ([7956d21](https://github.com/elixir-europe-training/ELIXIR-TrP-KG-training-metadata/commit/7956d21745d315d8dec8ea71beb57ec8adc86d16))

## [0.0.4-beta](https://github.com/elixir-europe-training/ELIXIR-TrP-KG-training-metadata/compare/0.0.3-beta..v0.0.4-beta) - 2025-11-10

### 🐛 Bug Fixes

- Fix harvest - ([aa4f2f7](https://github.com/elixir-europe-training/ELIXIR-TrP-KG-training-metadata/commit/aa4f2f7cb973e4abae04f6350d66f61b54e2ff33))

## [0.0.3-beta](https://github.com/elixir-europe-training/ELIXIR-TrP-KG-training-metadata/compare/v0.0.2-beta..0.0.3-beta) - 2025-11-06

## [0.0.2-beta](https://github.com/elixir-europe-training/ELIXIR-TrP-KG-training-metadata/compare/v0.0.1-beta..v0.0.2-beta) - 2025-11-06

### 🚜 Refactor

- Extract graph, parser, and dedupe helpers - ([8d60e04](https://github.com/elixir-europe-training/ELIXIR-TrP-KG-training-metadata/commit/8d60e04b08b89449961a26d002017928badac9e5))
- Delegate loader logic to new package - ([9a496a5](https://github.com/elixir-europe-training/ELIXIR-TrP-KG-training-metadata/commit/9a496a57261bc571314a51fa4cdb4d93b9c5e86d))
- Scaffold package for upcoming split - ([ef8336b](https://github.com/elixir-europe-training/ELIXIR-TrP-KG-training-metadata/commit/ef8336b2462e7872f4943b82a82cf7c5e335dfa4))
- Move lookup classes into dedicated modules - ([34ce281](https://github.com/elixir-europe-training/ELIXIR-TrP-KG-training-metadata/commit/34ce2812473d695ff8eab8115730a895df455fbe))

## [0.0.1-beta](https://github.com/elixir-europe-training/ELIXIR-TrP-KG-training-metadata/tree/v0.0.1-beta) - 2025-11-05

### ⛰️ Features

- Add mcp server proof of concept querying the TeSS API directly - ([6122103](https://github.com/elixir-europe-training/ELIXIR-TrP-KG-training-metadata/commit/6122103274f10814638a8915565488362a061b84))
- Script to harvest tess data and create a ttl rdf file, added a markdown files with SPARQL queries to use on it - ([9378029](https://github.com/elixir-europe-training/ELIXIR-TrP-KG-training-metadata/commit/93780295601609d580c76f0278711c997a6b87e3))
- Add harvested tess data to repo - ([ca605e7](https://github.com/elixir-europe-training/ELIXIR-TrP-KG-training-metadata/commit/ca605e7713dbde8c7fdf2c87312e418ae5871988))
- Add harvested tess data to repo - ([8454af2](https://github.com/elixir-europe-training/ELIXIR-TrP-KG-training-metadata/commit/8454af22ef664cb1f6ee88aadb156f92b04f8fdf))
- Normalize schema.org URLs and keep richest resource variant - ([ff4e917](https://github.com/elixir-europe-training/ELIXIR-TrP-KG-training-metadata/commit/ff4e9177573de96abed76a37f12bbb89d29de3bb))
- Extract rich person/topic metadata from GTN structures - ([8bbb1db](https://github.com/elixir-europe-training/ELIXIR-TrP-KG-training-metadata/commit/8bbb1db0ddb1c7a417d6f6b4a52c072441285fd1))
- Surface accessibility and audience metadata for training resources - ([db7c66e](https://github.com/elixir-europe-training/ELIXIR-TrP-KG-training-metadata/commit/db7c66e7844cbc005a59de869a4e9fae6f0d87a0))
- Expose aggregate load stats on TrainingDataStore - ([8ed5373](https://github.com/elixir-europe-training/ELIXIR-TrP-KG-training-metadata/commit/8ed537394f0cf54aa27e7997f19cf0d3cd052b5c))
- Enrich tess data with SIB org ROR IRI - ([15d0c85](https://github.com/elixir-europe-training/ELIXIR-TrP-KG-training-metadata/commit/15d0c85059a7c5482b6aeb02c1a1eed3a4d9115c))
- Add local search tools backed by harvested data - ([93fd469](https://github.com/elixir-europe-training/ELIXIR-TrP-KG-training-metadata/commit/93fd46906298b5f9b1333b9c20e57a6d492cc8ae))

### 🐛 Bug Fixes

- Resolve harvested data paths relative to project root - ([9e92c23](https://github.com/elixir-europe-training/ELIXIR-TrP-KG-training-metadata/commit/9e92c23c21c04d7fbee7af3dddfb304f6d4822e2))

### 📚 Documentation

- Fix tool instructions typo and clarify http port usage - ([aedd144](https://github.com/elixir-europe-training/ELIXIR-TrP-KG-training-metadata/commit/aedd1442d3e3e6cd0e92e3343007c2124dbe1264))

### 🛠️ Miscellaneous Tasks

- Improve rdflib endpoint cmd - ([5d03d13](https://github.com/elixir-europe-training/ELIXIR-TrP-KG-training-metadata/commit/5d03d132c161510fee5c7953d126221c4136b4d0))
- Replace legacy gtn harvest file with latest export - ([40e052c](https://github.com/elixir-europe-training/ELIXIR-TrP-KG-training-metadata/commit/40e052c1463fc53e21d5c7431f26e205fb060fda))

<!-- generated by git-cliff -->
