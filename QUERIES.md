# SPARQL Queries for Training Materials

This document contains SPARQL queries to search through the ELIXIR training materials RDF data.

Run the script to harvest JSON-LD data (takes ~30min due to parsing JSON-LD being expensive):

```sh
uv run src/elixir_training_mcp/harvest.py
```

Deploy a SPARQL endpoint on http://localhost:8000

```sh
uv run rdflib-endpoint serve data/tess_harvested_data.ttl
```

## 1. Find all Python courses

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

## 2. Find courses by location and date range

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
}
ORDER BY ?startDate
```

## 3. Find courses with specific learning outcomes

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

## 4. Find all courses provided by a specific organization

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

## 5. Find courses with prerequisites

```sparql
PREFIX schema: <http://schema.org/>

SELECT ?course ?name ?prerequisites
WHERE {
  ?course a schema:Course ;
          schema:name ?name ;
          schema:coursePrerequisites ?prerequisites .
}
```

## 6. Find courses by capacity and course mode

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
}
ORDER BY DESC(?capacity)
```

## 7. Find courses with multiple funding organizations

```sparql
PREFIX schema: <http://schema.org/>

SELECT ?course ?name (COUNT(?funder) as ?funderCount) ?funderNames
WHERE {
  ?course a schema:Course ;
          schema:name ?name ;
          schema:hasCourseInstance ?instance .
  ?instance schema:funder ?funderOrg .
  ?funderOrg schema:name ?funderNames .
}
GROUP BY ?course ?name
HAVING(COUNT(?funder) > 1)
```

## 8. Find courses organized by a specific person

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

## 9. Find courses with specific keywords or topics

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

## 10. Find upcoming courses near a geographic location

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
}
ORDER BY ?startDate
```
