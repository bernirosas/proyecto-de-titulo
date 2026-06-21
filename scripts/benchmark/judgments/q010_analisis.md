# Análisis del juicio LLM — q010

**Query**: *"Inscripción de la compraventa en el Conservador de Bienes Raíces como tradición del dominio del inmueble"*
**Área**: Compraventa de bienes raíces
**Modelo juez**: `gemini-2.5-flash-lite`
**Fecha del juicio**: 2026-06-13
**Chunks evaluados**: 32

## Distribución de grados

| Grado | Cantidad | Porcentaje |
|-------|---------:|-----------:|
| 3 (altamente relevante) | 14 | 44% |
| 2 (relevante) | 9 | 28% |
| 1 (marginal) | 4 | 12% |
| 0 (irrelevante) | 5 | 16% |
| -1 (parse error) | 0 | 0% |

Es la query mejor cubierta del set (23 chunks ≥2, 14 de ellos grado 3). Concuerda con la cobertura del corpus: "Conservador de Bienes Raíces" aparece en 484 chunks y la inscripción como modo de adquirir el dominio es a la vez materia del Código Civil y tema recurrente en oficios SII (la inscripción determina quién es el contribuyente). Por eso casi todas las técnicas rinden alto.

## Aciertos

- `0ff3174a` (g3): la adquisición y enajenación de bienes raíces se entienden inscritas en el Conservador.
- `5c75b362` (g3): la adquisición y enajenación se perfeccionan con la inscripción en el Conservador.
- `9bd9461d` (g3): la transferencia de dominio de bienes raíces requiere inscripción en el Conservador.

Grado 0 correctos: arrendamientos e impuesto territorial (`754d8152`), adquisición por Fisco/Municipalidades (`0bf34689`), tasaciones (`0cfb800e`) — mencionan bienes raíces pero no la inscripción como tradición.

## Incidencia técnica del juez y corrección manual

El chunk `a30d90c2` (Resolución Exenta SII N°8655, Formulario 2890) devolvió **parse-error (`-1`) del LLM en todas las corridas** — un fallo determinista de parseo de ese chunk en particular, no del resto del batch (los otros 4 chunks de su batch se juzgaron sin problema en cada corrida). Conforme al procedimiento de la guía (sección 5.1, "Cuándo sobreescribir el juicio del LLM"), se asignó su grado por **revisión humana**:

- `a30d90c2` → **grado 1**, con la nota `[corregido manualmente: el LLM devolvió parse-error (-1) en todas las corridas; grado asignado por revisión humana según escala TREC]`. El chunk trata el procedimiento administrativo-tributario para que Notarías y Conservadores informen las enajenaciones al SII; menciona inscripción y Conservador pero no la inscripción como tradición del dominio, de ahí el grado marginal.

**Correcciones manuales: 1** (el caso anterior, por parse-error, no por desacuerdo con un grado del juez).

> Nota operativa: el juicio de q010 se completó con una key de Gemini distinta a la de q006–q009 (cuota diaria del proyecto original agotada). El modelo es el mismo (`gemini-2.5-flash-lite`), por lo que la consistencia del juez se mantiene. Los 31 grados automáticos se ensamblaron tomando, por chunk, el grado de cualquier corrida exitosa del mismo modelo (los `-1` intermedios eran fallos de infraestructura 403/429, no decisiones del juez).

## Resultados de `evaluate_query.py`

**Técnica ganadora por top-10 mean_grade: `p1_bm25` (2.800)**, empatada con `p1_tfidf` (2.800).

| Observación | Detalle |
|---|---|
| Casi todas altas | seis técnicas ≥ 2.6 en top-10 (query "fácil", muy cubierta) |
| P3 TF-IDF perfecta en medio | p3_tfidf top-5 mean 3.0 y P@5 = 1.0 |
| SPLADE competitivo | 2.600 top-10 (mejor que en q008/q009) |
| Baseline último otra vez | 0.700 top-10 — su mejor cifra del set, aun así el peor de las 8 |

A diferencia de q008 (donde BM25 ≫ SPLADE), aquí la brecha entre técnicas es pequeña: el vocabulario "inscripción / Conservador / tradición / dominio" es compartido entre consulta y documentos, así que tanto el match léxico como la expansión semántica aciertan.

## Conclusión

Juicios utilizables como ground truth. Distribución excelente (44% grado 3), extremos bien clasificados y una única corrección manual documentada por parse-error del LLM. Baja discriminación entre técnicas (todas convergen alto), coherente con ser la consulta de mayor cobertura en el corpus.
