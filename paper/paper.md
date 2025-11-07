---
title: 'Mining the potential of knowledge graphs for metadata on training'
title_short: 'Mining Knowledge Graphs for Training Metadata'
tags:
  - knowledge graphs
  - metadata
  - training
authors:
  - name: Vincent Emonet
    orcid: 0000-0002-1501-1082
    affiliation: 1
  - name: Harshita Gupta
    affiliation: 3
    orcid: 0009-0000-1141-3116
  - name: Dimitris Panouris
    affiliation: 3
    orcid: 0009-0005-2282-2982
  - name: Jacobo Miranda
    affiliation: 4
    orcid: 0009-0005-0673-021X
  - name: Phil Reed
    affiliation: 2
    orcid: 0000-0002-4479-715X
  - name: Jerven Bolleman
    orcid: 0000-0002-7449-1266
    affiliation: 1
  - name: Finn Bacall
    affiliation: 2
    orcid: 0000-0002-0048-3300
  - name: Geert van Geest
    affiliation: 1
    orcid: 0000-0002-1561-078X

affiliations:
  - name: SIB Swiss Institute of Bioinformatics, Switzerland
    index: 1
    ror: 002n09z45
  - name: University of Manchester, UK
    index: 2
    ror: 027m9bs27
  - name: SciLifeLab, Sweden
    index: 3
    ror: 04ev03g22
  - name: EMBL Heidelberg, Germany
    index: 4
    ror: 03mstc592

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

In this project, we represented training metadata stored in TeSS as a queryable knowledge graph. By doing so, we were able to find relevant gaps in the metadata that put a contstraint on knowledge graph definitions. To access and query the knowledge graph using large language models (LLM) we developed a model context protocol (MCP) server. Finally, we defined user stories to evaluate the potential of the tool, including construction of custom learning paths, creation of detailed trainer profiles, and connection of training metadata to other databases. These use-cases also shed light on the limits on the currently available metadata, and will help to make future choices on better defined and richer metadata.

# From Bioschemas to knowledge graphs

In order to create a knowledge graph we extracted training metadata from two resources:
- TeSS (https://tess.elixir-europe.org/): The ELIXIR Training e-Support System (TeSS) is a platform that aggregates training materials, courses, and events from various providers across Europe. TeSS uses the Bioschemas Training profile to annotate its resources with standardized metadata.
- Galaxy training network (https://training.galaxyproject.org/): The Galaxy Training Network (GTN) provides a collection of training materials and tutorials for the Galaxy platform. The GTN also uses the Bioschemas Training profile to annotate its resources.

Although the Galaxy training network metadata is already available in TeSS, we extracted it separately, as it contains identitifiers for trainers that are not available from TeSS at the moment. In this way, we could evaluate the impact of having trainer identifiers.

While going through the process of building a knowledge graph, we acknowledged that there is large potential to improve the available metadata unique identifiers. Which is also stated in the FAIR principles, stating that digital resources, i.e., data and metadata, are assigned a globally unique and persistent identifier. Ideally, the metadata providers associate permanent identifiers for courses, events and course materials that can be preserved between systems. This would for instance allow merging of Bioschemas data that have overlapping course instances. In addition, Organizations could be identified by their [ROR](https://ror.org/) and teachers by [ORCID](https://orcid.org) when available. During the hackathon we worked on merging such nodes, and bringing this data cleaning effort back to the different teams. Our specific suggestions for metadata providers can be found in the individual subchapters below. 

### About and keywords

In the about and keywords properties it is recommended to use ontologies, which would be EDAM in the case of Bioschemas. This is already implemented in TeSS and by many other metadata providers, but for completeness, we mention it here. Example:

```json
"about": [
    {
        "@id": "http://edamontology.org/topic_3474",
        "@type": "DefinedTerm",
        "inDefinedTermSet": "http://edamontology.org",
        "termCode": "topic_3474",
        "url": "http://edamontology.org/topic_3474",
        "name": "Machine learning"
    }
]
```

### Persons and organisations

In properties like:

- author
- instructor
- contributor
- funder
- organiser

We typically specify persons and organisations. Frequently used identifiers for these are ORCiD and ROR respectively. Example:

```json
"author": [
    {
        "@type": "Person",
        "@id": "https://orcid.org/0000-0002-1501-1082",
        "name": "Vincent Emonet"
    },
    {
        "@type": "Organization",
        "@id": "https://ror.org/002n09z45",
        "name": "SIB Swiss Institute of Bioinformatics"
    }
]
```

### Location

For identifying the location, we recommend using OpenStreetMap (OSM) URLs, which can be either:

- **Node** – a single geographic point defined by latitude and longitude.
- **Way** – an ordered sequence of nodes that creates a polyline (e.g., a road) or a closed polygon (e.g., a building outline).
- **Relation** – a container that groups nodes, ways, or  other relations together with specific roles to represent complex  structures such as routes, boundaries, or turn restrictions.

Typically, a way would be used to define a building, and a relation for more complex structures, including cities or countries. Example:

```json
"location": {
    "@type": "Place",
    "@id": "https://www.openstreetmap.org/relation/1684625",
    "address": {
        "@type": "PostalAddress",
        "addressLocality": "Bellinzona",
        "addressCountry": "Switzerland"
    }
}
```

# MCP server

To facilitate access to the knowledge graph by AI systems and humans, we developed a Model Context Protocol (MCP) server that exposes a suite of tools for searching and querying training materials. The MCP server provides both live and offline search capabilities. The live tool `search_training_materials` directly queries the TeSS platform via its API. For offline access to the harvested and deduplicated knowledge graph, we implemented six search tools: `keyword_search` enables free-text searches across training resources, `provider_search` filters materials by provider organization, `location_search` finds courses by geographic location, `date_search` identifies courses within a specified date range, and `topic_search` filters by subject matter using ontology terms. Additionally, the `dataset_stats` tool provides high-level diagnostics about the loaded datasets. For advanced use cases, the server exposes `execute_sparql_query`, which allows users to formulate and execute custom SPARQL queries directly against the knowledge graph. These tools together enable flexible querying of training metadata through natural language interfaces, supporting both simple discovery tasks and complex analytical queries.

# Defining user stories and testing

To work towards a valuable end-user experiences, we created a list of user stories. These are potential user experiences that are written in the following format:

- As a [user persona]
- I want to [do task]
- …so that [outcome/benefit]

Examples of the defined user stories are:

- As a trainer of visualisation techniques

-  want to find other trainers in Germany and France

- …so that I can collaborate on developing new training events for our national audiences

Or:

- As a bioinformatics scientist
- want to define a learning path of training materials and/or events
- …so that I can become a specialist in artificial intelligence within a specified amount of time and resources (e.g. I have 6 months, workload of 14 days, I can travel within Europe once)

 These user stories were directly used as prompts to test the tool. For some user stories we added additional prompts, such as 'Provide the urls of the training material data' or 'Report only materials that are on GitHub'. Responses of the chatbot can be found in the repository.

# Discussion

# Future work

- Host the knowledge graph on a public SPARQL endpoint to allow users to query the data directly.
- Host a chatbot that connects to the MCP server for easier access to the training materials knowledge graph.
- Extend the knowledge graph by integrating additional data sources, such as trainer profiles and related publications.


## Acknowledgements

We thank the organizers of the Biohackathon Europe 2025 for organizing the event and travel support for some of the authors.

## Supplemental information

We use pandoc flavoured markdown, similar to Rstudio see \url{https://garrettgman.github.io/rmarkdown/authoring_pandoc_markdown.html}.


## References
