# SPARQL Queries for Training Materials

This document contains SPARQL queries to search through the ELIXIR training materials RDF data.

Deploy a SPARQL endpoint on http://localhost:8000:

```sh
uv run rdflib-endpoint serve data/*_harvest.ttl
```

> [!NOTE]
>
> The `data/tess_harvest.ttl` files is included in the repository (7MB), you can run the script to harvest JSON-LD data and build this ttl file, but it takes ~30min due to parsing JSON-LD being expensive:
>
> ```sh
> uv run src/elixir_training_mcp/harvest.py
> ```
>

> [!NOTE]
>
> TeSS contains training materials and courses from various providers, such as GTN (Galaxy Training Network) training materials. Metadata about material in TeSS and GTN can be matched on `schema:url`

## Find all Python courses

```sparql
PREFIX schema: <http://schema.org/>
PREFIX dct: <http://purl.org/dc/terms/>

SELECT ?course ?name ?description
WHERE {
  ?course a schema:Course ;
           schema:name ?name ;
           schema:description ?description .
  FILTER(CONTAINS(LCASE(?name), "python") || CONTAINS(LCASE(?description), "python"))
}
```

## Find courses by location and date range

```sparql
PREFIX schema: <http://schema.org/>

SELECT ?course ?name ?country ?locality ?startDate ?endDate
WHERE {
  ?course a schema:Course ;
          schema:name ?name ;
          schema:hasCourseInstance ?instance .
  ?instance schema:location ?location ;
            schema:startDate ?startDate ;
            schema:endDate ?endDate .
  ?location schema:address ?address .
  ?address schema:addressCountry ?country ;
           schema:addressLocality ?locality .
  FILTER(?startDate >= "2025-11-01"^^xsd:date && ?endDate <= "2025-12-31"^^xsd:date)
} ORDER BY ?startDate
```

## Find courses with specific learning outcomes

```sparql
PREFIX schema: <http://schema.org/>

SELECT ?course ?name ?teaches
WHERE {
  ?course a schema:Course ;
          schema:name ?name ;
          schema:teaches ?teaches .
  FILTER(CONTAINS(LCASE(?teaches), "ansible") || CONTAINS(LCASE(?teaches), "galaxy"))
}
```

## Find all courses provided by a specific organization

```sparql
PREFIX schema: <http://schema.org/>

SELECT ?course ?name ?provider
WHERE {
  ?course a schema:Course ;
          schema:name ?name ;
          schema:provider ?providerOrg .
  ?providerOrg schema:name ?provider .
  FILTER(?provider = "GTN" || ?provider = "Bioinformatics.ca")
}
```

## Find courses with prerequisites

```sparql
PREFIX schema: <http://schema.org/>

SELECT ?course ?name ?prerequisites
WHERE {
  ?course a schema:Course ;
          schema:name ?name ;
          schema:coursePrerequisites ?prerequisites .
}
```

## Find courses by capacity and course mode

```sparql
PREFIX schema: <http://schema.org/>

SELECT ?course ?name ?mode ?capacity ?country
WHERE {
  ?course a schema:Course ;
          schema:name ?name ;
          schema:hasCourseInstance ?instance .
  ?instance schema:courseMode ?mode ;
            schema:maximumAttendeeCapacity ?capacity ;
            schema:location ?location .
  ?location schema:address ?address .
  ?address schema:addressCountry ?country .
  FILTER(?capacity > 20)
} ORDER BY DESC(?capacity)
```

## Find courses with multiple funding organizations

```sparql
PREFIX schema: <http://schema.org/>

SELECT ?course ?name (COUNT(?funder) as ?funderCount) ?funderNames
WHERE {
  ?course a schema:Course ;
          schema:name ?name ;
          schema:hasCourseInstance ?instance .
  ?instance schema:funder ?funderOrg .
  ?funderOrg schema:name ?funderNames .
} GROUP BY ?course ?name HAVING(COUNT(?funder) > 1)
```

## Find courses organized by a specific person

```sparql
PREFIX schema: <http://schema.org/>

SELECT ?course ?name ?organizer
WHERE {
  ?course a schema:Course ;
          schema:name ?name ;
          schema:hasCourseInstance ?instance .
  ?instance schema:organizer ?organizerOrg .
  ?organizerOrg schema:name ?organizer .
  FILTER(CONTAINS(?organizer, "Martin Čech"))
}
```

## Find courses with specific keywords or topics

```sparql
PREFIX schema: <http://schema.org/>
PREFIX edam: <http://edamontology.org/>

SELECT ?course ?name ?keywords ?topics
WHERE {
  ?course a schema:Course ;
          schema:name ?name .
  OPTIONAL { ?course schema:keywords ?keywords . }
  OPTIONAL { ?course schema:about ?topics . }
  FILTER(CONTAINS(LCASE(?keywords), "admin") || CONTAINS(LCASE(?keywords), "galaxy"))
}
```

## Find upcoming courses near a geographic location

```sparql
PREFIX schema: <http://schema.org/>

SELECT ?course ?name ?locality ?distance ?startDate
WHERE {
  ?course a schema:Course ;
          schema:name ?name ;
          schema:hasCourseInstance ?instance .
  ?instance schema:location ?location ;
            schema:startDate ?startDate .
  ?location schema:latitude ?lat ;
            schema:longitude ?lon ;
            schema:address ?address .
  ?address schema:addressLocality ?locality .
  # Filter for courses in Canada as example
  FILTER(CONTAINS(?locality, "Toronto") || CONTAINS(?locality, "Halifax") || CONTAINS(?locality, "Vancouver"))
} ORDER BY ?startDate
```
