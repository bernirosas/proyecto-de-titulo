# =============================================================================
# Queries útiles para chunks_maqui — pegue todo en Dev Tools de OpenSearch
# Dashboards (http://localhost:5601/app/dev_tools#/console).
#
# Cada bloque está precedido por un comentario `#` que explica qué hace,
# y utiliza ejemplos concretos del corpus Maqui (ley, oficio, circular,
# resolución, jurisprudencia; fuentes SII y BCN; temas tributarios y
# constitucionales).
#
# Puede ejecutar uno solo posicionando el cursor sobre él y presionando ▶,
# o todos seguidos.
# =============================================================================


# -----------------------------------------------------------------------------
# 1. INSPECCIÓN BÁSICA DEL CORPUS
# -----------------------------------------------------------------------------

# Total de chunks indexados (esperado: 61842).
GET chunks_maqui/_count

# Cantidad de documentos lógicos únicos (cardinality sobre document_id).
# Cada `document_id` agrupa todos los chunks de una misma ley/oficio/etc.
GET chunks_maqui/_search
{
  "size": 0,
  "aggs": {
    "docs_unicos": { "cardinality": { "field": "document_id" } }
  }
}

# Distribución de chunks por subtipo: ley, oficio, circular, resolucion, jurisprudencia.
# Esto reproduce el censo del corpus que sustentó la decisión del MER v3.
GET chunks_maqui/_search
{
  "size": 0,
  "aggs": {
    "por_tipo": { "terms": { "field": "source_type", "size": 20 } }
  }
}

# Distribución por fuente emisora (ej: SII, BCN, Poder Judicial).
GET chunks_maqui/_search
{
  "size": 0,
  "aggs": {
    "por_fuente": { "terms": { "field": "source", "size": 20 } }
  }
}

# Estadísticas del largo de chunk en caracteres — sanity check de la chunkización.
GET chunks_maqui/_search
{
  "size": 0,
  "aggs": {
    "largo": { "stats": { "field": "char_length" } }
  }
}

# Percentiles de char_length (p50, p90, p95, p99) — distribución de tamaños.
# Si p99 está muy cerca del p50, los chunks son uniformes; si no, hay outliers.
GET chunks_maqui/_search
{
  "size": 0,
  "aggs": {
    "percentiles_largo": {
      "percentiles": {
        "field": "char_length",
        "percents": [50, 90, 95, 99]
      }
    }
  }
}


# -----------------------------------------------------------------------------
# 2. TRAER DOCUMENTOS PUNTUALES
# -----------------------------------------------------------------------------

# Recuperar un chunk por su UUID exacto.
# Tip: ejecute primero la consulta "Primeros 5 chunks" más abajo para obtener un UUID real.
GET chunks_maqui/_doc/00000000-0000-0000-0000-000000000000

# Todos los chunks de un mismo documento lógico, ordenados por chunk_id.
# Útil para reconstruir un documento completo (ej: el texto íntegro de una ley).
# Reemplace el document_id por uno real obtenido de las consultas de exploración.
GET chunks_maqui/_search
{
  "size": 100,
  "query": { "term": { "document_id": "doc_ley_19880" } },
  "sort": [{ "chunk_id": "asc" }]
}

# Buscar el documento por su filename exacto (ej: SII_19164_ROL_4-2023).
GET chunks_maqui/_search
{
  "size": 5,
  "query": { "term": { "filename": "SII_19164_ROL_4-2023" } }
}

# Buscar por external_id parseado del filename (ej: número de pronunciamiento SII).
GET chunks_maqui/_search
{
  "size": 5,
  "query": { "term": { "external_id": 19164 } }
}

# Primeros 5 chunks del corpus — útil para inspeccionar el formato de los
# datos y obtener UUIDs/document_ids reales con los cuales experimentar.
GET chunks_maqui/_search
{
  "size": 5,
  "_source": ["chunk_uuid", "document_id", "source_type", "name", "content"],
  "query": { "match_all": {} }
}


# -----------------------------------------------------------------------------
# 3. RECUPERACIÓN BM25 (lo central de la tesis)
# -----------------------------------------------------------------------------

# Match básico sobre `content`. El score que devuelve es BM25.
# Con el analizador `spanish_legal` esto pasa por lowercase + stop + stemmer.
# Ejemplo: notificación electrónica, central en Ley 19.880 de procedimientos.
GET chunks_maqui/_search
{
  "size": 5,
  "query": { "match": { "content": "notificación electrónica" } }
}

# Match con highlights — muestra qué tokens del documento matchearon la query.
# Ejemplo tributario: prescripción de la acción de cobro.
GET chunks_maqui/_search
{
  "size": 3,
  "query": { "match": { "content": "prescripción de la acción de cobro" } },
  "highlight": {
    "fields": { "content": { "fragment_size": 150, "number_of_fragments": 2 } }
  }
}

# Match con operator AND — exige que TODOS los términos aparezcan
# (en vez del default OR). Más preciso, menos cobertura.
# Ejemplo: queremos chunks que mencionen impuesto Y valor Y agregado.
GET chunks_maqui/_search
{
  "size": 5,
  "query": {
    "match": {
      "content": { "query": "impuesto al valor agregado", "operator": "and" }
    }
  }
}

# Match phrase — exige que las palabras aparezcan EN ORDEN y contiguas.
# Más estricto que match con AND. Ideal para frases técnicas legales.
# Ejemplo: "renta líquida imponible" es un término exacto del Art. 31 LIR.
GET chunks_maqui/_search
{
  "size": 5,
  "query": {
    "match_phrase": { "content": { "query": "renta líquida imponible" } }
  }
}

# Match phrase con slop — permite hasta N palabras intermedias.
# Útil cuando el orden importa pero puede haber un adjetivo en medio.
GET chunks_maqui/_search
{
  "size": 5,
  "query": {
    "match_phrase": {
      "content": { "query": "recurso protección", "slop": 2 }
    }
  }
}

# Multi_match buscando en `content` y `name` con boost en `name`.
# Si el término aparece en el nombre del documento, pesa el triple.
# Ejemplo: una "circular sobre exención" probablemente se titula así.
GET chunks_maqui/_search
{
  "size": 5,
  "query": {
    "multi_match": {
      "query": "exención tributaria",
      "fields": ["content", "name^3"]
    }
  }
}


# -----------------------------------------------------------------------------
# 4. RECUPERACIÓN FILTRADA (búsqueda libre + filtros estructurados)
# -----------------------------------------------------------------------------

# Buscar SOLO entre jurisprudencia. `filter` no contribuye al score, solo recorta.
# Ejemplo clásico: recursos de protección.
GET chunks_maqui/_search
{
  "size": 5,
  "query": {
    "bool": {
      "must":   [ { "match": { "content": "recurso de protección" } } ],
      "filter": [ { "term":  { "source_type": "jurisprudencia" } } ]
    }
  }
}

# Múltiples filtros: tipo + fuente. Solo circulares emitidas por el SII.
GET chunks_maqui/_search
{
  "size": 5,
  "query": {
    "bool": {
      "must":   [ { "match": { "content": "IVA exportación" } } ],
      "filter": [
        { "term": { "source_type": "circular" } },
        { "term": { "source": "SII" } }
      ]
    }
  }
}

# Filtro por rango de fechas — leyes promulgadas desde 2020 sobre modernización tributaria.
GET chunks_maqui/_search
{
  "size": 5,
  "query": {
    "bool": {
      "must":   [ { "match": { "content": "modernización tributaria" } } ],
      "filter": [
        { "term":  { "source_type": "ley" } },
        { "range": { "publication_date": { "gte": "2020-01-01" } } }
      ]
    }
  }
}

# Combinar filtro por tribunal específico + tema.
# Ejemplo: jurisprudencia de la Corte Suprema sobre garantías constitucionales.
GET chunks_maqui/_search
{
  "size": 5,
  "query": {
    "bool": {
      "must":   [ { "match": { "content": "garantías constitucionales" } } ],
      "filter": [
        { "term": { "source_type": "jurisprudencia" } },
        { "term": { "court_specific_name": "Corte Suprema" } }
      ]
    }
  }
}

# Filtro por rol_number (sólo aplica a jurisprudencia).
GET chunks_maqui/_search
{
  "size": 5,
  "query": {
    "bool": {
      "filter": [
        { "term": { "source_type": "jurisprudencia" } },
        { "term": { "rol_number": "ROL_4-2023" } }
      ]
    }
  }
}


# -----------------------------------------------------------------------------
# 5. AGREGACIONES (entender el corpus)
# -----------------------------------------------------------------------------

# Top 10 tribunales por cantidad de chunks (solo aplica a jurisprudencia).
GET chunks_maqui/_search
{
  "size": 0,
  "query": { "term": { "source_type": "jurisprudencia" } },
  "aggs": {
    "top_tribunales": {
      "terms": { "field": "court_specific_name", "size": 10 }
    }
  }
}

# Distribución temporal de leyes por año.
GET chunks_maqui/_search
{
  "size": 0,
  "query": { "term": { "source_type": "ley" } },
  "aggs": {
    "por_anio": {
      "date_histogram": {
        "field": "publication_date",
        "calendar_interval": "year"
      }
    }
  }
}

# Cross-tab: por cada source_type, top 5 instancias (instance_name).
# La rama de jurisprudencia debería ser la única con valores no nulos.
# Es la validación visual de la dependencia funcional source_type→instance_name.
GET chunks_maqui/_search
{
  "size": 0,
  "aggs": {
    "por_tipo": {
      "terms": { "field": "source_type", "size": 20 },
      "aggs": {
        "instancias": {
          "terms": { "field": "instance_name", "size": 5 }
        }
      }
    }
  }
}

# Cantidad de documentos lógicos únicos por tribunal (no chunks).
# Diferencia importante: un fallo largo aporta varios chunks pero 1 documento.
GET chunks_maqui/_search
{
  "size": 0,
  "query": { "term": { "source_type": "jurisprudencia" } },
  "aggs": {
    "tribunales": {
      "terms": { "field": "court_specific_name", "size": 5 },
      "aggs": {
        "docs_unicos": { "cardinality": { "field": "document_id" } }
      }
    }
  }
}

# Top 10 oficios del SII por cantidad de chunks (proxy de extensión).
GET chunks_maqui/_search
{
  "size": 0,
  "query": {
    "bool": {
      "filter": [
        { "term": { "source_type": "oficio" } },
        { "term": { "source": "SII" } }
      ]
    }
  },
  "aggs": {
    "top_oficios": {
      "terms": { "field": "external_id", "size": 10 }
    }
  }
}


# -----------------------------------------------------------------------------
# 6. VALIDACIÓN DE DEPENDENCIAS FUNCIONALES DEL MER
# -----------------------------------------------------------------------------

# rol_number SOLO debería existir en jurisprudencia (FD validada en el censo).
# Si aparece otro source_type acá, hay un dato inconsistente — punto a defender.
GET chunks_maqui/_search
{
  "size": 0,
  "query": { "exists": { "field": "rol_number" } },
  "aggs": {
    "tipos_con_rol": { "terms": { "field": "source_type", "size": 10 } }
  }
}

# bcn_id_norm SOLO debería existir en ley (su count debería igualar el de leyes).
GET chunks_maqui/_search
{
  "size": 0,
  "query": { "exists": { "field": "bcn_id_norm" } },
  "aggs": {
    "tipos_con_bcn": { "terms": { "field": "source_type", "size": 10 } }
  }
}

# Detectar anomalías: jurisprudencia que NO tiene rol_number.
# En un MER limpio, este resultado debería ser vacío.
GET chunks_maqui/_search
{
  "size": 5,
  "query": {
    "bool": {
      "must":     [ { "term":   { "source_type": "jurisprudencia" } } ],
      "must_not": [ { "exists": { "field": "rol_number" } } ]
    }
  }
}

# Detectar anomalías: leyes que NO tienen bcn_id_norm.
GET chunks_maqui/_search
{
  "size": 5,
  "query": {
    "bool": {
      "must":     [ { "term":   { "source_type": "ley" } } ],
      "must_not": [ { "exists": { "field": "bcn_id_norm" } } ]
    }
  }
}

# Detectar anomalías cruzadas: oficios o circulares con court_specific_name.
GET chunks_maqui/_search
{
  "size": 5,
  "query": {
    "bool": {
      "must":   [ { "exists": { "field": "court_specific_name" } } ],
      "must_not": [ { "term":  { "source_type": "jurisprudencia" } } ]
    }
  }
}


# -----------------------------------------------------------------------------
# 7. EXPLORACIÓN PARA CONSTRUIR EL QUERY SET DE EVALUACIÓN
# -----------------------------------------------------------------------------

# Top-hits por source_type: trae 2 ejemplos representativos de cada tipo.
# Útil para curar queries diversas a partir del corpus real (las 15-20 por tipo
# que la tesis necesita).
GET chunks_maqui/_search
{
  "size": 0,
  "aggs": {
    "por_tipo": {
      "terms": { "field": "source_type", "size": 10 },
      "aggs": {
        "ejemplos": {
          "top_hits": {
            "size": 2,
            "_source": ["name", "content"]
          }
        }
      }
    }
  }
}

# Buscar un término técnico para entender cómo aparece en el corpus.
# El highlight muestra el contexto, lo que ayuda a redactar buenas queries.
GET chunks_maqui/_search
{
  "size": 10,
  "query": { "match": { "content": "habeas corpus" } },
  "_source": ["source_type", "name"],
  "highlight": { "fields": { "content": {} } }
}

# Otro tema candidato: tributación de criptomonedas (transversal).
GET chunks_maqui/_search
{
  "size": 10,
  "query": { "match": { "content": "criptomonedas activos digitales" } },
  "_source": ["source_type", "name"],
  "highlight": { "fields": { "content": {} } }
}

# Tema candidato para query set: facturación electrónica (clásico SII).
GET chunks_maqui/_search
{
  "size": 10,
  "query": { "match_phrase": { "content": "factura electrónica" } },
  "_source": ["source_type", "name", "filename"],
  "highlight": { "fields": { "content": {} } }
}


# -----------------------------------------------------------------------------
# 8. VERIFICAR EL ANALIZADOR EN ESPAÑOL
# -----------------------------------------------------------------------------

# Validar que el stemmer normaliza singular/plural: ambos counts deberían ser
# similares (no idénticos por casos de stop words alrededor, pero del mismo orden).
GET chunks_maqui/_count
{ "query": { "match": { "content": "notificaciones" } } }

GET chunks_maqui/_count
{ "query": { "match": { "content": "notificación" } } }

# Validar stemming de verbos: "tributar" / "tributario" / "tributación".
GET chunks_maqui/_count
{ "query": { "match": { "content": "tributario" } } }

GET chunks_maqui/_count
{ "query": { "match": { "content": "tributación" } } }

# Inspeccionar exactamente cómo el analizador `spanish_legal` tokeniza una frase.
# Devuelve la lista de tokens tal como quedan indexados (sin tildes? con stem?).
GET chunks_maqui/_analyze
{
  "analyzer": "spanish_legal",
  "text": "Las notificaciones electrónicas serán válidas según el artículo 11 bis"
}

# Comparar con el analizador estándar — para evidenciar el efecto del stemmer.
GET chunks_maqui/_analyze
{
  "analyzer": "standard",
  "text": "Las notificaciones electrónicas serán válidas según el artículo 11 bis"
}


# -----------------------------------------------------------------------------
# 9. PREPARACIÓN PARA SPLADE / TF-IDF (rank_features, hoy vacíos)
# -----------------------------------------------------------------------------

# Confirmar que los campos sparse_tfidf y sparse_splade están declarados.
GET chunks_maqui/_mapping/field/sparse_tfidf,sparse_splade

# Plantilla de query con rank_feature — así se buscará una vez que se carguen
# los pesos por término. `feature` es el nombre del término dentro del campo
# rank_features (ej: sparse_splade.notificación = 0.87).
GET chunks_maqui/_search
{
  "size": 5,
  "query": {
    "rank_feature": {
      "field": "sparse_splade.notificación"
    }
  }
}

# Combinación BM25 + SPLADE en una sola query híbrida (futuro).
# Suma el score de match con el score del rank_feature para un término.
# Esta es la estructura que va a usar la tesis para el experimento híbrido.
GET chunks_maqui/_search
{
  "size": 5,
  "query": {
    "bool": {
      "should": [
        { "match":        { "content": "notificación electrónica" } },
        { "rank_feature": { "field":   "sparse_splade.notificación" } },
        { "rank_feature": { "field":   "sparse_splade.electrónica" } }
      ]
    }
  }
}


# -----------------------------------------------------------------------------
# 10. MANTENIMIENTO Y SALUD DEL ÍNDICE
# -----------------------------------------------------------------------------

# Forzar refresh — hace visibles para búsqueda los docs recién indexados.
POST chunks_maqui/_refresh

# Estado del cluster (verde = ok, amarillo = sin réplicas, rojo = problema).
# En un single-node como el nuestro, "yellow" es lo esperado.
GET _cluster/health

# Listar todos los índices con tamaño y cantidad de docs (cat API legible).
GET _cat/indices?v

# Ver shards del índice y su estado.
GET _cat/shards/chunks_maqui?v

# Estadísticas internas del índice (uso de disco, segments, refresh, etc).
GET chunks_maqui/_stats

# Borrar TODOS los documentos de un source_type — útil para reingestar parcial.
# CUIDADO: es destructivo. Comentado por seguridad.
# POST chunks_maqui/_delete_by_query
# {
#   "query": { "term": { "source_type": "circular" } }
# }