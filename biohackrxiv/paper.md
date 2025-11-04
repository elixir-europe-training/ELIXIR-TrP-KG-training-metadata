---
title: 'Mining the potential of knowledge graphs for metadata on training'
title_short: 'Mining Knowledge Graphs for Training Metadata'
tags:
  - knowledge graphs
  - metadata
  - training
authors:
  - name: Vincent Emonet
    orcid: 
    affiliation: 1
  - name: Harshita Gupta
    affiliation: 3
    orcid: 
  - name: Dimitris Panouris
    affiliation: 3
    orcid: 
  - name: Jacobo Miranda 
    affiliation: 4
    orcid: 
  - name: Phil Reed
    affiliation: 2
    orcid: 
  - name: Jerven Bolleman
    orcid: 0000-0002-7449-1266
    affiliation: 1
  - name: Finn Bacall
    affiliation: 2
    orcid: 
  - name: Geert van Geest
    affiliation: 1
    orcid: 

affiliations:
  - name: SIB Swiss Institute of Bioinformatics, Switzerland
    index: 1
  - name: University of Manchester, UK
    index: 2
  - name: SciLifeLab, Sweden
    index: 3
  - name: EMBL Heidelberg, Germany
    index: 4
    ror: 

date: 4 November 2025
cito-bibliography: paper.bib
event: biohackathon2025
biohackathon_name: "BioHackathon Europe 2025"
biohackathon_url:   "https://biohackathon-europe.org/"
biohackathon_location: "Bad-Saarow, Germany, 2025"
group: Logic programming group
# URL to project git repo --- should contain the actual paper.md:
git_url: https://github.com/elixir-europe-training/ELIXIR-TrP-KG-training-metadata
# This is the short authors description that is used at the
# bottom of the generated paper (typically the first two authors):
authors_short: Vincent Emonet, Harshita Gupta et al.
---


<!--

The paper.md, bibtex and figure file can be found in this repo:

  https://github.com/journal-of-research-objects/Example-BioHackrXiv-Paper

To modify, please clone the repo. You can generate PDF of the paper by
pasting above link (or yours) in

  http://biohackrxiv.genenetwork.org/

-->

# Introduction

Knowledge graphs (KGs) can greatly increase the potential of data by revealing hidden relationships and turning it into useful information. A KG is a graph-based representation of data that stores relations between subjects, predicates and objects in triplestores. These entities are typically described in pre-defined ontologies, which increase interoperability and connect data that would otherwise remain isolated in siloed databases. This structured data representation can greatly facilitate complex querying and applications to deep learning approaches like generative AI.

ELIXIR and its Nodes are making a major effort to make the wealth of open training materials on the computational life sciences reusable, amongst others by guidelines and support for annotating training materials with standardized metadata. One major step in standardizing metadata is the use of the Bioschemas training profile, which became a standard for representing training metadata. Despite being standardized and interoperable, there is still a lot of potential to turn these resources into valuable information, linking training data across various databases.

In this project, we represented training metadata stored in TeSS as queryable knowledge graphs. After that we a developed a model context protocol (MCP) server to access and search through the knowledge graph using a natural language interface. Finally, we defined user stories to evaluate the potential of the tool, including construction of custom learning paths, creation of detailed trainer profiles, and connection of training metadata to other databases. These use-cases also shed light on the limits on the currently available metadata, and will help to make future choices on better defined and richer metadata.

# From bioschemas to knowledge graphs

Bioschemas are RDF and so should be a knowledge graph already. However, while it is technically a graph, there is a lack of knowledge. 
We see that many nodes in the graph as extracted from existing systems have no identity. For example Organizations could be identified by their [ROR](https://ror.org/) and teachers by [ORCID](https://orcid.org) when available. Instead we have 100's of nodes in the graph about the same concepts (e.g. SIB Swiss Institute of Bioinformatics) but no shared identity. During the hackathon we worked on merging such nodes, and bringing this data cleaning effort back to the different teams.

# MCP server

# Defining and evaluating user stories

# Discussion



## Acknowledgements

We thank the organizers of the Biohackathon Europe 2025 for organizing the event and travel support for some of the authors.

## Supplemental information

We use pandoc flavoured markdown, similar to Rstudio see \url{https://garrettgman.github.io/rmarkdown/authoring_pandoc_markdown.html}.


## References
