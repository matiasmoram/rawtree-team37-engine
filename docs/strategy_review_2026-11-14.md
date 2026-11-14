# Revisión de estrategias para la final

**Corte:** 14 nov 2026, 17:53 CET. **Objetivo:** separar lo que ya está en el motor de lo que merece un experimento antes de la final. Las cifras de otros datasets o simuladores no predicen directamente el score de RawTree.

## Estado real

- El emisor activo (PID 31448) tomó el relevo a las 17:45:35 con `lgbm-recent:45,cf-v1:20,cf-rot:15,skibidy-v1:20`. `ev-v2-nocovis` ya no recibe tráfico del emisor local y se retiró del registro de políticas. Sus submissions siguen apareciendo temporalmente en la ventana móvil.
- Salud local a las 17:53: 1.446 requests respondidas, 1.358 enviadas, 8 fallos de push, 86 tardías y 7 errores. El artefacto público de las 17:46 marcaba al equipo con conversión 1,293 por 100, cold 1,714, puntualidad 80,9 % y puesto 10/42. Esa ventana aún contiene tráfico previo y muchas requests sin submission; no es una medida del nuevo mix.
- En la ventana pública móvil de las 17:51, los registros por modelo eran: `lgbm-recent` 1,478/100 (n=3.468), `cf-v1` 1,433 (n=2.557), `cf-rot` 1,251 (n=837), `skibidy-v1` 1,123 (n=158) y `ev-v2-nocovis` 1,639 (n=1.800). Las ventanas se solapan con el tráfico anterior; Skibidy tiene muy poca muestra. **No promocionar ni declarar ganador con estos datos.**

## Qué ya tenemos y qué falta activar

| Técnica | Estado comprobado en nuestro repo | Próximo paso |
|---|---|---|
| Vecinos de contenido y prior prestado para productos nuevos | `ContentIndex` lee `cache/new_product_neighbors.json`; `CartFirstPolicy` los usa para candidatos/calidad y `lgbm-recent` incluye candidatos de contenido. | Mantenerlo. El artefacto se generó el 15:33; comprobar cómo actualizarlo para productos creados durante la final y medir cobertura/recall de candidatos nuevos. |
| Co-visitas recientes | Existe `recent_covis.py`, un artefacto de 6 h con half-life de 6 h y una policy `ev-recent-covis`. | No está en los brazos activos y no había refresher corriendo al revisar. Programar refresco y probarlo solo con un corte point-in-time; las co-visitas del snapshot principal no son un refresco instantáneo. |
| Popularidad por device/región y lift de subcategoría/marca | Existe `engine/contextual.py`, su builder y `contextual.json`. `ev-context` aparece en un cambio local sin commit; el artefacto observado se generó a las 16:47. | Añadir refresco de la policy/artifact, medir solo nuevos usuarios y home, y después probar 10–15 % como challenger. No asumir que ese tráfico representa la distribución de la final. |
| Calibración durante el servicio | `refresh_calibration.py` ajusta multiplicadores acotados con impresiones realmente mostradas; `lgbm-recent` recarga el JSON. | El artefacto disponible era de las 17:22 y no se veía un refresher activo. Arrancar el job con su intervalo mínimo prudente y vigilar antigüedad/soporte; no calibrar scores heurísticos como si fueran probabilidades. |
| Exploración con propensiones | `TailExplorePolicy` conserva los ocho primeros puestos y aleatoriza los dos últimos con probabilidades explícitas; el runner escribe metadata local en `logs/exposure_metadata.jsonl`. No está en el mix activo. | Tras cerrar el ensayo actual, probarla con 5 % de requests y ventana fija. Unir cada fila a feedback y a la lista realmente enviada antes de IPS/OPE. Las propensiones son condicionales al brazo, pool y slate base. |
| Thompson sampling online | `skibidy-v1` está activo al 20 %. Aprende con feedback maduro (120 s), solo si el submission atribuido coincide exactamente con `t37-skibidy-v1`; se corrigió la atribución ambigua entre slates idénticos. | Dejar recoger muestra. No llamarlo OPE: no registra la propensión exacta de cada slate y su exploración afecta más que los slots 9–10. Compararlo en el leaderboard con horizonte fijo. |
| Promoción automática / failover remoto | El gate de `engine/experiments.py` falla cerrado y requiere una comparación de horizonte fijo; no cambia brazos automáticamente. El heartbeat local declara `distributed_lease: false`. | Mantener promoción manual. Para dos máquinas hace falta lease/ownership compartido verificable; dos procesos con `shard-count=1` duplican submissions. |
| Logistic Thompson (`tslogit`) | `engine/online/tslogit.py` y `scripts/train_tslogit.py` son prototipo local sin registro en el servicio. | No desplegar aún. Corregir la estandarización con split temporal (ahora estima media/desviación con toda la ventana) y medir ranking/compra en slot 1, calibración e intervalos agrupados por usuario; AUC puede reflejar el slot. |

## Estrategias priorizadas

1. **Terminar el ensayo actual sin cambiar brazos repetidamente.** Fijar ahora una hora de cierre, auditar emisores y comparar una sola ventana común. Mantener un guard de puntualidad; si cae, priorizar fiabilidad sobre experimentar. Skibidy n=158 es aún diagnóstico.
2. **Activar `ev-context` para tráfico sin historia.** Es el hueco más concreto frente al equipo Toni: popularidad suavizada por device/región y tendencias por subcategoría/marca ya tienen builder, policy y un artefacto. Primero refresco + replay point-in-time en `new_user`/home; luego brazo pequeño. La diferencia esperada es sobre el componente cold-start, pero es una hipótesis hasta verla en el score de RawTree.
3. **Dar cobertura a artículos realmente nuevos.** El uso de embeddings está resuelto para productos presentes en el artefacto, pero una inserción del catálogo posterior al último build puede no tener vecinos. Medir cuántos `new_product` quedan cubiertos; actualizar vecinos solo después de cargar descripción/catálogo y mantener `known_at` para no filtrar futuro.
4. **Después, explorar solo slots 9–10 con `ev-content-tail`.** Mantiene estable el tramo de mayor valor y registra probabilidades de selección. Arrancar con epsilon 0,05, muestras maduras y análisis preregistrado. Usar IPS/DR únicamente cuando la propensity registrada corresponde al slate servido.
5. **Mantener co-visitas/calibración como jobs explícitos, no como supuestas capacidades live.** Son piezas implementadas, pero su utilidad depende de que los artefactos se actualicen y no excedan sus edades máximas.

## Investigación externa

- La solución de ToniOrtizGil es la referencia pública más cercana porque documenta el mismo reto y servicio. Sus descripciones de slot 9–10, calibración, contexto y heartbeat son ideas de diseño, no evidencia independiente de lift; su propio README advierte que varias cifras vienen de simulación. [Repositorio del equipo](https://github.com/ToniOrtizGil/rawtree-recsys-fme2026).
- Los repos de [OTTO de Theo Viel](https://github.com/TheoViel/kaggle_otto_rs) y [Nicolai Vicol](https://github.com/nicolaivicol/otto-recommender) respaldan una arquitectura retrieval + reranking con fuentes/ranks separados, co-visitas y similitud de items. OTTO medía Recall/MRR por sesión; sus resultados no se trasladan a compras esperadas por request.
- [Deezer Carousel Bandits](https://github.com/deezer/carousel_bandits) aporta ejemplos de feedback online y posición en un carrusel; su reward era consumo/streaming, no compra. [EACB](https://arxiv.org/abs/2408.04332) estudia sesgo de exposición en bandits en cascada; apoya tratar slots distintos de forma distinta, no una cifra de mejora en este simulador.
- [Open Bandit Pipeline](https://zr-obp.readthedocs.io/en/latest/index.html) documenta IPS/SNIPS/DR para logs con propensiones; refuerza que un hash de asignación de brazo no basta para evaluar la probabilidad de una lista ordenada.
- [RecList](https://github.com/RecList/reclist) propone tests conductuales por cohortes. Podemos adoptar sus ideas con tests propios: usuario sin historia, producto nuevo, ningún artículo comprado/inactivo, diversidad y cobertura del origen de cada candidato.
- Para texto, los model cards de [BGE-small-en-v1.5](https://huggingface.co/BAAI/bge-small-en-v1.5), [all-MiniLM-L6-v2](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2) y [E5-small-v2](https://huggingface.co/intfloat/e5-small-v2) describen encoders compactos. No cambiar el embedding existente por popularidad de Hugging Face: comparar recall temporal de productos nuevos y calidad de vecinos en nuestro catálogo.

## Límite de evidencia

Los resultados de OTTO, Deezer, Hugging Face y papers son referencias externas. La métrica que decide es el score público de RawTree (compras esperadas por 100 requests; cold-start y puntualidad separados, revenue como desempate). El replay de listas observadas y los AUC offline son diagnósticos, no estimadores del score contrafactual del simulador.

## Fuente interna

La investigación del equipo sobre el stream y las relaciones entre historial, carrito y compras está en [Notion: Research recomanador — team 37 (Jordi)](https://www.notion.so/418c8c86cbf0811dbceef898148d4939).
