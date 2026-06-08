# Guía de uso de `testRAG.ipynb`

Este documento explica cómo:

1. Configurar `config/config_chroma.json`.
2. Ejecutar `testRAG.ipynb` de principio a fin.
3. Lanzar pruebas con `tests/input.json`.
4. Generar resultados en `tests/output.json` y evaluación en `tests/eval_report.json`.

## 1) Tecnologías usadas

- ChromaDB:
  - Vectorstore local para almacenar embeddings, metadatos (`categoria`, `page_number`, `section_name`) y permitir recuperación semántica.
- LangGraph:
  - Orquestación del flujo RAG por nodos (`AgentNode`, `GradeDocumentsNode`, `GenerateNode`, etc.).
- DeepEval:
  - Framework de evaluación para medir calidad del RAG (relevancia, faithfulness, correctness y similitud de páginas).
- Model providers validados:
  - La solución se ha probado con modelos de Hugging Face y con Azure OpenAI.
  - Para una mejor experiencia en la parte de evaluación (`DeepEval`), se recomienda usar un modelo GPT desplegado en Azure OpenAI (por estabilidad y consistencia en las métricas).


## 2) Configuración obligatoria antes de empezar

Antes de ejecutar el notebook, configura credenciales y claves API:

1. Edita `config/config_chroma.json` con valores reales:
   - `models.azure_openai.endpoint`
   - `models.azure_openai.api_key`
   - `models.azure_openai.api_version`
   - `models.azure_openai.embeddings.deployment_name`
   - `models.azure_openai.llm.deployment_name`
2. Si vas a usar Hugging Face o Gemini, completa también sus claves en `models.huggingface` o `models.gemini`.
3. Verifica que el proveedor activo (`models.provider`) coincide con la sección que has configurado.

Si estas claves no están bien configuradas, fallarán la inicialización del modelo, la ejecución del orquestador y la evaluación.

## 3) Requisitos previos

- Python 3.10+
- Dependencias instaladas desde:
  - `requirements.txt`
- VS Code con soporte de Jupyter (o Jupyter Lab)

Instalación rápida (desde la carpeta `prueba`):

```bash
pip install -r requirements.txt
```

## 4) Cómo ejecutar (end-to-end)

Flujo mínimo recomendado:

1. Configura credenciales y modelos en `config/config_chroma.json`.
2. Prepara documentos en `data/pdf/<categoria>/*.pdf`.
3. Define casos en `tests/input.json`.
4. Ejecuta el notebook `testRAG.ipynb` en orden (ver sección de celdas).
5. Revisa resultados en:
  - `tests/output.json`
  - `tests/eval_report.json`

Resultado esperado del pipeline:

- Ingesta + vectorización local en ChromaDB.
- Ejecución del flujo RAG por nodos con LangGraph.
- Evaluación automática de calidad y grounding con DeepEval.

## 5) Estructura esperada

- Notebook de ejecución:
  - `testRAG.ipynb`
- Configuración:
  - `config/config_chroma.json`
- Preguntas de prueba:
  - `tests/input.json`
- Salidas generadas:
  - `tests/output.json`
  - `tests/eval_report.json`
- Documentos fuente para indexar:
  - `data/pdf/<categoria>/*.pdf`

La categoría se toma del nombre de carpeta bajo `data/pdf`.
Ejemplo: `data/pdf/legal/mi_doc.pdf` tendrá `categoria = "legal"`.

## 6) Configuración de `config_chroma.json`

Archivo: `config/config_chroma.json`

### 6.1 Bloque `models`

Define proveedor de embeddings/LLM.

#### Opción Azure OpenAI (actual)

```json
{
  "models": {
    "provider": "azure_openai",
    "azure_openai": {
      "endpoint": "https://<tu-endpoint>.openai.azure.com/",
      "api_key": "<tu-api-key>",
      "api_version": "2024-02-01",
      "embeddings": {
        "deployment_name": "text-embedding-3-large"
      },
      "llm": {
        "deployment_name": "gpt-4.1-mini",
        "temperature": 0
      }
    }
  }
}
```

Campos clave:

- `models.provider`: proveedor activo (`azure_openai`, `huggingface`, `gemini`).
- `azure_openai.endpoint`: endpoint del recurso Azure OpenAI.
- `azure_openai.api_key`: clave de API.
- `azure_openai.api_version`: versión API.
- `azure_openai.embeddings.deployment_name`: deployment de embeddings.
- `azure_openai.llm.deployment_name`: deployment del chat model.

### 6.2 Bloque `vectorstore`

```json
{
  "vectorstore": {
    "provider": "chroma",
    "chroma": {
      "collection_name": "testRAG_azure",
      "persist_directory": "./chroma_db_azure"
    }
  }
}
```

Campos clave:

- `vectorstore.provider`: en este notebook debe ser `chroma`.
- `chroma.collection_name`: nombre de colección.
- `chroma.persist_directory`: carpeta persistente del índice.

### 6.3 Bloques `retriever` y `rag`

`retriever.search_kwargs.k` controla el número de resultados (`top-k`) por consulta.

```json
{
  "retriever": {
    "search_type": "similarity",
    "search_kwargs": {
      "k": 4,
      "filter": {
        "categoria": "legal"
      }
    }
  }
}
```

Nota importante sobre `filter.categoria`:

- En el notebook, el `retriever_tool` aplica filtro dinámico por la `categoria` de cada pregunta de `input.json`.
- Ese filtro dinámico prevalece en ejecución cuando la pregunta incluye `categoria`.

## 7) Formato de `tests/input.json`

Cada elemento de prueba debe tener este patrón:

```json
{
  "question": "Texto de la pregunta",
  "expected_answer": "Respuesta esperada de referencia",
  "expected_references": ["NombreDocumento.pdf, page 7"],
  "categoria": "informes"
}
```

Recomendaciones:

- `expected_references` en formato string: `"<archivo>, page <n>"`.
- `categoria` debe existir en el árbol `data/pdf/<categoria>/...`.
- Usa preguntas en el idioma objetivo del sistema (actualmente español en el grafo).

## 8) Orden de ejecución de `testRAG.ipynb`

Ejecuta las celdas en este orden:

1. Celda 2: carga de `config_chroma.json`, creación de embeddings/LLM/vectorstore.
2. Celda 4: ingesta de PDFs y creación de chunks con metadatos (`categoria`, `page_number`, `section_name`).
3. Celda 7: carga de prompts desde `data/prompts`.
4. Celda 8: función para normalizar la salida pública.
5. Celda 9: definición de `retriever_tool` con filtro por categoría.
6. Celda 10: ejecución batch con `tests/input.json` y guardado en `tests/output.json`.
7. Celda 13: inicialización de métricas DeepEval.
8. Celda 14: evaluación batch y guardado en `tests/eval_report.json`.

## 9) Decisiones técnicas

### 9.1 Por qué ChromaDB

- Es local y persistente:
  - Permite trabajar offline/local sin depender de un servicio gestionado para las pruebas.
- Es simple de operar en notebook:
  - Colecciones, persistencia y consulta semántica con poca fricción.
- Soporta metadatos y filtros:
  - Se aprovecha `categoria` para restringir recuperación por tipo de documento.
- Facilita iteración rápida:
  - Con `CLEAN_START` se puede reconstruir índice de forma reproducible.

### 9.2 Por qué LangGraph

- El flujo RAG es explícito y controlable por nodos:
  - Decisión, recuperación, grading de documentos, generación, reescritura y sugerencias.
- Mejora trazabilidad y depuración:
  - Es más fácil ver en qué etapa falla o degrada una respuesta.
- Encaja con evolución futura:
  - Permite ajustar o reemplazar nodos sin rediseñar toda la pipeline.

### 9.3 Por qué DeepEval

- Evalúa calidad de respuesta con métricas LLM-as-judge.
- Permite combinar evaluación semántica con validación de referencias.
- Se integra bien con ejecución batch desde `tests/output.json`.

### 9.4 Filtrado por categoría y mejora recomendada

Estado actual del filtrado:

- El pipeline usa filtro por `categoria` en retrieval.
- En pruebas batch, la `categoria` llega desde cada caso de `tests/input.json`.
- Este enfoque funciona bien si la categoría está bien definida a priori.

Mejora ideal (recomendada): detección previa de intención/área de la pregunta

- Antes de recuperar documentos, ejecutar un clasificador de categoría que estime la clase más probable (`legal`, `manuales`, `informes`, etc.).
- Opciones técnicas viables:
  - Clasificación con LLM (zero-shot/few-shot) para mayor flexibilidad semántica.
  - Clasificación supervisada con BERT/Transformers para mayor estabilidad y coste predecible en inferencia.
- Con esa categoría predicha, aplicar filtro de retrieval automáticamente.

Beneficios esperados:

- Menos ruido documental al restringir búsqueda al dominio correcto.
- Mejor precisión de referencias (documento/página).
- Mejor calidad global de respuesta en preguntas ambiguas o sin categoría explícita.

Recomendación práctica de despliegue:

1. Introducir nodo previo de "intent/category detection" en el flujo de LangGraph.
2. Guardar en estado:
   - `predicted_categoria`
   - `confidence`
3. Estrategia híbrida según confianza:
   - alta confianza: filtrar por categoría predicha.
   - baja confianza: búsqueda mixta (sin filtro estricto o top-2 categorías).
4. Medir impacto con DeepEval comparando baseline vs. pipeline con clasificación previa.

## 10) Configurabilidad y evolución futura

El diseño se ha orientado a que la solución sea configurable sin rehacer la pipeline:

1. Configuración centralizada por JSON:
  - `config/config_chroma.json` concentra proveedor, modelos, vectorstore y parámetros de recuperación.
2. Proveedores de modelos intercambiables:
  - La factoría de modelos permite cambiar entre Azure OpenAI, Hugging Face y Gemini según coste, calidad, latencia o disponibilidad.
3. API keys y credenciales desacopladas del código:
  - Se inyectan por configuración para poder rotar credenciales y cambiar entornos con menor impacto.
4. Parámetros de retrieval ajustables:
  - `k`, filtros por `categoria` y otros parámetros permiten optimizar precisión/recall sin tocar lógica de negocio.
5. Base preparada para experimentación:
  - Es posible comparar alternativas de embeddings/LLM y validar resultados con la misma batería de casos y métricas.

Objetivo de esta configurabilidad:

- Encontrar la mejor alternativa técnica según contexto (coste, calidad, velocidad, gobernanza).
- Facilitar mantenimiento y escalado futuro sin romper compatibilidad con el flujo actual.

## 11) Métricas usadas

En evaluación se usan dos grupos de métricas:

1. Métricas de contenido (DeepEval):
   - `AnswerRelevancyMetric`
   - `FaithfulnessMetric`
   - `ContextualRelevancyMetric`
   - `GEval` (Correctness)
2. Métrica de referencias/páginas:
   - `compute_page_similarity` compara páginas esperadas vs recuperadas con tolerancia (`PAGE_TOLERANCE`).
   - Aporta señal de grounding documental además de la calidad textual.

## 12) Manejo de documentos

Reglas de ingesta y estructura:

1. Ubicación:
   - `data/pdf/<categoria>/*.pdf`
2. Segmentación:
   - Se parsea cada PDF por página y se hace chunking (`chunk_size=1200`, `chunk_overlap=150`).
3. Metadatos indexados por chunk:
   - `categoria`, `source_file`, `source_path`, `page_number`, `page_name`, `section_name`, `chunk_id`.
4. Salidas auxiliares:
   - HTML por página en `data/pdf/html_pages`.
5. Reindexación:
   - `CLEAN_START = True` para reconstruir colección y evitar duplicados entre ejecuciones.

### 12.1 Estrategia de chunking aplicada

Se utiliza `RecursiveCharacterTextSplitter` con:

- `chunk_size = 1200`
- `chunk_overlap = 150`

Decisiones y justificación:

1. Tamaño de chunk (`1200`):
   - Busca un equilibrio entre contexto suficiente y precisión de recuperación.
   - Chunks demasiado pequeños pierden contexto semántico; demasiado grandes diluyen relevancia.
2. Solape (`150`):
   - Reduce cortes bruscos entre fragmentos consecutivos.
   - Ayuda a preservar continuidad cuando una idea queda entre dos chunks.
3. Diseño orientado a retrieval:
   - Mejora probabilidad de recuperar pasajes completos y citables para el RAG.

### 12.2 Particionado por página y sección

Antes del chunking, el pipeline divide por página y aprovecha HTML para inferir secciones:

1. Paginado explícito:
   - Cada chunk conserva `page_number` y `page_name`.
2. Extracción de estructura desde HTML:
   - Se detectan encabezados (`h1`-`h6`) y, como fallback, texto con mayor tamaño de fuente.
   - Esto alimenta `section_name` para mejorar trazabilidad.
3. Beneficio práctico:
   - Las respuestas pueden anclarse mejor a documento, sección y página.
   - Facilita validación posterior de grounding y similitud de páginas en evaluación.

## 13) Qué genera cada fase

### 13.1 Ingesta

- Crea/actualiza la colección Chroma con chunks y metadatos.
- Guarda HTML por página en `data/pdf/html_pages`.

### 13.2 Ejecución de pruebas

- Lee `tests/input.json`.
- Ejecuta el orquestador por cada caso.
- Escribe `tests/output.json` con:
  - `actual_output`
  - `actual_references`
  - `status` (`ok`, `error`, `skipped_empty_question`)

### 13.3 Evaluación DeepEval

- Lee `tests/output.json`.
- Evalúa métricas de contenido (relevancia, faithfulness, correctness, etc.).
- Calcula similitud de páginas con tolerancia (`PAGE_TOLERANCE`).
- Escribe `tests/eval_report.json` con resumen y detalle por caso.

## 14) Ciclo recomendado de trabajo

1. Ajusta `config/config_chroma.json`.
2. Revisa/edita `tests/input.json`.
3. Ejecuta celdas 2 -> 10 para generar `tests/output.json`.
4. Ejecuta celdas 13 -> 14 para generar `tests/eval_report.json`.
5. Analiza errores/casos flojos y repite.

## 15) Troubleshooting rápido

- Error de credenciales Azure:
  - Verifica `endpoint`, `api_key`, `api_version` y deployments en `config_chroma.json`.
- Cero documentos recuperados:
  - Confirma que la carpeta `data/pdf/<categoria>` existe y que la categoría del input coincide.
  - Aumenta `retriever.search_kwargs.k`.
- Resultados mezclados de pruebas anteriores:
  - Deja `CLEAN_START = True` en la celda de ingesta para reconstruir colección.
- Evaluación no arranca:
  - Ejecuta antes la celda 13 (métricas) y comprueba que `tests/output.json` exista.

## 16) Seguridad y buenas prácticas

- No subas claves reales a Git.
- Sustituye valores sensibles por variables de entorno o placeholders.
- Mantén separados índices por proveedor/modelo de embeddings (colecciones distintas en Chroma).
