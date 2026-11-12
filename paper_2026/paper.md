---
title: 'Training Resources AI-driveN Exploration Repository (ELIXIR TRAINER)'
title_short: 'ELIXIR TRAINER'
tags:
  - knowledge graphs
  - metadata
  - training
authors:
  - name: Vincent Emonet
    orcid: 0000-0002-1501-1082
    affiliation: 2
    role: Software, Data curation, Validation, Writing, Conceptualization, Funding acquisition, Supervision
  - name: Phil Reed
    affiliation: 4
    orcid: 0000-0002-4479-715X
    role: Data curation, Resources, Validation, Writing, Conceptualization, Supervision
  - name: Panayiotis Smeros
    affiliation: 1
    orcid: 0009-0004-5814-5824
    role: Software, Data curation, Visualization, Writing, Conceptualization, Supervision
  - name: Ana Osojnik 
    affiliation: 3
    orcid: 0000-0001-6691-2959
    role: Software, Data curation, Validation, Writing
  - name: Jerven Bolleman
    orcid: 0000-0002-7449-1266
    affiliation: 1
    role: Data curation, Validation
  - name: Finn Bacall
    affiliation: 2
    orcid: 0000-0002-0048-3300
    role: Data curation, Resources, Validation
  - name: Geert van Geest
    affiliation: 1
    orcid: 0000-0002-1561-078X
    role: Data curation, Validation, Writing, Conceptualization, Funding acquisition, Supervision

affiliations:
  - name: SIB Swiss Institute of Bioinformatics, Switzerland
    index: 1
    ror: 002n09z45
  - name: The University of Manchester, UK
    index: 2
    ror: 027m9bs27
  - name: Leibniz Institute DSMZ-German Collection of Microorganisms and Cell Cultures GmbH
    index: 3
    ror: 02tyer376


date: 12 November 2025
cito-bibliography: paper.bib
event: biohackathon2026
biohackathon_name: "BioHackathon Europe 2026"
biohackathon_url:   "https://biohackathon-europe.org/"
biohackathon_location: "Barcelona, Spain, 2026"
group: Project 15
# URL to project git repo --- should contain the actual paper.md:
git_url: https://github.com/elixir-europe-training/ELIXIR-TrP-KG-training-metadata
# This is the short authors description that is used at the
# bottom of the generated paper (typically the first two authors):
authors_short: Vincent Emonet, Phil Reed, et al.
---

\setlength{\textfloatsep}{12pt}
\setlength{\abovecaptionskip}{10pt}
\setlength{\belowcaptionskip}{8pt}

# Introduction

Training registries such as ELIXIR TeSS, Glittr.org and SciLifeLab Training contain a rich body of metadata describing training materials, events, and contributors across the life‑science and biomedical domains. Although this information is represented in RDF, it remains insufficiently interconnected with other knowledge resources and is not easily discoverable or queryable by end users or automated systems. As a result, much of its potential value for learners, trainers, and research infrastructure professionals remains untapped.

The Training Resources AI-driveN Exploration Repository (TRAINER) project picks up from previous work[@panouris_2025] to deliver training metadata from three registries on one public knowledge graph, ready for people and AI agents. It **integrates** TeSS, Glittr and SciLifeLab, harmonized, following the TRX metadata model[@trx_2026]. 
It is **interactive**, answering SPARQL queries or plain language questions via its MCP server and interactive widgets. 
It is **publicly available** (in the short term), providing a live endpoint with example queries, with automatic updates possible. 

We focus on improving data quality, interoperability, and reusability across existing training registries. Author identification and attribution is strengthened by leveraging persistent identifiers such as ORCID, enabling rich, reusable contributor profiles, while shared schemas are used to harmonize metadata. By following SIB best practices for exposing SPARQL endpoints, including example queries and clear schemas, the KG ia FAIR, self-describing, and easily reusable by downstream users and services.

A key innovation is enabling direct interaction with the linked data through a conversational interface. The training KG and servers are temporarily hosted thanks to SIB. For TRAINER to be implemented as a permanent, complementary service to ELIXIR TeSS, further discussions are required regarding hosting arrangements and costs. Such an offer would improve cross‑resource discovery, visibility, and sustainability, supporting reuse by humans and agents.


# From training repositories to knowledge graph-based interactive user interfaces



## Source registries and metadata models

We provided training materials and events from three sources: 
- [ELIXIR TeSS Portal](https://tess.elixir-europe.org/)
  - TeSS now serves a dump of all materials and events in JSON-LD, replacing the harvesting tool developed at BioHackathon 2025. This saves a 30 minutes harvesting that queried thousands of pages.
- [Glittr.org](https://glittr.org/)
- [SciLifeLab Training Portal](https://training.scilifelab.se/)

ELIXIR TeSS and Glittr use Bioschemas profiles to describe learning resources ([TrainingMaterial](https://bioschemas.org/profiles/TrainingMaterial/1.0-RELEASE)) and events ([Course](https://bioschemas.org/profiles/Course/1.0-RELEASE), [CourseInstance](https://bioschemas.org/profiles/CourseInstance/1.0-RELEASE)).

(TODO: shall we share the JSON-LD endpoints here?)

## Harmonization of schemas

We used the TRX minimum metadata model for Training Registry eXchange[@trx_2026] to map the properties from SciLifeLab to ELIXIR TeSS and Bioschemas. This model allowed us to harmonize the properties which is essential for consistency in the knowledge graph.

(TODO: how did we map SciLifeLab?)

## Inspirational models and interfaces

(TODO: SIB queries, Claude things)


# System architecture and pipeline

(TODO: subheadings copied from 2025 paper)

## Offline processing pipeline

## Data model and indexes

## MCP server


### Tool execution lifecycle


# Putting user stories into practice
The user-stories defined in 2025 were revisited and refreshed, including a more realistic query for Bioconductor. The user stories were then transformed to runnable SPARQL queries and to visualisation widgets.

(TODO: some details about the transformation)


![Project timeline and validation phases. A link to the full diagram is available at the supplemental information.](./diagrams/project-timeline.cropped.pdf)

(TODO: graphic from last year, note these are Mermaid mmd diagrams and we predict the URL of the PDF render that is made every time we build the paper.)

# Discussion

(TODO: What interesting things happened, what is their significance? What were the challenges, what could we not do and why? What are the security risks and how did we address them (or mention this in the architecture section)?)

# Future work

(TODO: What would be required to make this a live ELIXIR service? What are the options here eg embed within ELIXIR TeSS or standalone site? How could this be used beyond ELIXIR? What features will be developed next? What other opportunities are there eg dashboard for TeSS?)


## Acknowledgements

We thank the organizers of the BioHackathon Europe 2026 for putting on the event and travel support for some of the authors. We thank Alma Nilsson, Maria Doyle, Sebastian Lobentanzer, and Project 6 for providing suggestion, help and inspiration.


## Supplemental information

- Tools deployed publicly
  - SPARQL endpoint: <https://biosoda.unil.ch/elixir-trainer/sparql>
  - MCP server: <https://biosoda.unil.ch/elixir-trainer/mcp>
  - Chat UI that uses the MCP server: <https://biosoda.unil.ch/elixir-trainer/>
- [GitHub repository](https://github.com/elixir-europe-training/ELIXIR-trainer)
- [Google sheet](https://docs.google.com/spreadsheets/d/19XxU7RF_A9EwVn52FfFpj4qWr7521ETYnIJ7lcIB4ho/edit?gid=0#gid=0) with user stories
- Diagrams:
  - [Figure 5. Project timeline](https://github.com/elixir-europe-training/ELIXIR-trainer/blob/main/paper_2026/diagrams/project-timeline.mmd)

## References
