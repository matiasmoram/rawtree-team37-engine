# Decisión: un ranker de compra con recuperación de candidatos

**Fecha:** 14 noviembre 2026. **Estado:** decisión adoptada; siguiente modelo pendiente de entrenar.

## Decisión

Dejamos de mantener una colección de políticas independientes. El sistema objetivo será un único flujo de dos etapas:

1. **Recuperación**: formar un conjunto pequeño de productos válidos a partir del carrito sin comprar, las vistas recientes de la sesión, afinidad histórica del usuario, vecinos de contenido de artículos nuevos y productos populares del contexto.
2. **Ranking**: estimar una probabilidad de compra por producto y ordenar los candidatos con un único modelo de compra. Aplicar exclusión dura de productos ya comprados y validar actividad/stock justo antes de enviar.

El objetivo de entrenamiento es `P(compra | request, producto)` para una exposición en posición de referencia 0. La lista observada y el feedback deben coincidir exactamente; la posición observada se conserva para aprender/corregir examen, pero no debe premiar artificialmente una posición al ordenar candidatos.

## Evidencia y decisiones de señal

| Señal o idea | Decisión | Razón |
|---|---|---|
| Producto comprado antes | Excluir | En el feedback real de Notion convirtió casi cero. Evita desperdiciar los 10 espacios. |
| Carrito aún no comprado | Prioridad alta | La investigación interna estima una tasa muy superior a los productos sin relación. Debe ser candidato y feature del ranker, no solo una regla opaca. |
| Vistas recientes de sesión | Prioridad alta | El feedback real muestra una señal útil; conservar orden y recencia como features. |
| Historial usuario/categoría | Usar como prior suavizado | Da cobertura a requests sin señales de sesión y generaliza mejor que IDs. |
| Calidad de producto, categoría y contexto | Usar con suavizado y fecha de corte | Evita que contadores escasos o futuros dominen. Device/región son features de challenger hasta tener evaluación propia. |
| Vecinos de contenido | Mantener como fuente de candidatos y prior de cold start | Ya hay integración de servicio; los productos añadidos tras el artefacto pueden quedar fuera. Añadir cobertura y corte temporal al siguiente ciclo. |
| Co-visitas recientes | Aparcar | Hay artefactos y policy, pero la matriz no se refresca en el delta normal. El boost global anterior no ganó de forma estable. |
| Skibidy/Thompson y exploración | Sacar de servicio por ahora | Atribución y propensión de la lista no son suficientemente fiables para aprender/evaluar esta exploración. Guardar el prototipo; no llamarlo OPE. |
| `cf-rot` | Sacar del mix inicial | La muestra del leaderboard es pequeña y convive con emisores duplicados. La hipótesis de orden de vistas queda como challenger futuro, no como política adicional permanente. |
| Auto-promoción y tuning continuo | No activar | Ventanas solapadas y escritores simultáneos invalidan las decisiones automáticas. Revisión humana tras una ventana cerrada. |

## Próximo modelo: `lgbm-cart-v2`

La brecha concreta del ranker actual es que su generación de candidatos/features no usa estado del carrito, aunque el flujo cart-first sí. El siguiente entrenamiento debe añadir como candidatos y features PIT:

- `is_carted`, número de eventos de carrito, edad del último carrito y edad por bandas;
- orden de recencia de los artículos del carrito y coincidencia de subcategoría con la sesión;
- contribución separada de vista reciente, vista histórica y carrito;
- fuente/rango de recuperación, similitud del vecino y antigüedad del artefacto para candidatos de contenido;
- región y page context para calibración/cohortes, sin IDs de usuario o producto como atajos.

El constructor de dataset debe reconstruir el carrito estrictamente antes de cada request: estado anterior al inicio + eventos `add_to_cart` y `purchase` con timestamp menor al de la request. Si no se puede reconstruir ese punto en el tiempo, se omite el feature; no se rellena con estado actual.

Entrenar click y compra como objetivos separados y comparar `P(click) × P(compra | click)` con el objetivo directo de compra. Elegir en un bloque temporal de ajuste y calibrar en otro bloque distinto; reservar el último bloque cronológico como test intacto. El artefacto debe registrar corte, columnas, positivos por partición, calibración, cohortes cold/warm y hash de modelo.

## Validación y promoción

1. Resolver el ownership del tráfico: un escritor del equipo o shards disjuntos verificados. Ahora hay demasiadas requests con submissions de varias versiones; las comparaciones por brazo no son causalmente interpretables.
2. Mantener `lgbm-recent` como champion operativo y `cf-v1` como único comparator mientras se construye v2. El mix local queda `80/20`; se retiran `cf-rot` y `skibidy-v1` del default.
3. Hacer un replay point-in-time sobre una ventana nueva para comprobar cobertura de candidatos, listas válidas, latencia, cold start y orden de compras observadas. Ese replay es diagnóstico, no estimación del score oculto.
4. Exponer v2 como challenger pequeño, con una ventana fija, una sola asignación por usuario y mínimo preregistrado. Comparar conversión esperada RawTree, conversión cold y puntualidad en la misma ventana.
5. Promover solo tras terminar la ventana y auditar solapamiento de emisores, atribución exacta y fiabilidad. Sin promocionar por inspección repetida de ventanas móviles.

## Estado observado al decidir

El monitor de las 18:37 CET mostraba `lgbm-recent` 1,48 y `cf-rot` 1,56 compras esperadas por 100, pero con tamaños distintos (2.274 y 753) y ventanas móviles. El audit de 5 minutos encontró 56 % de requests con varios modelos; el de 15 minutos, 72 %. Esto impide afirmar que `cf-rot` sea mejor o que la asignación actual represente el tráfico que decide RawTree. Skibidy quedó claramente por debajo en la ventana larga, pero no basta para concluir sobre el modelo fuera de esa contaminación.

## No hacer todavía

- No desplegar un nuevo modelo solo porque mejore AUC: el ranker anterior mejoraba AUC pero no demostró mejor orden de compra.
- No mezclar ventanas temporales ni contar una request varias veces por tener varios submissions.
- No medir IPS/SNIPS/DR sin propensity correspondiente a la selección de la lista realmente mostrada.
- No reemplazar embeddings por otro encoder por popularidad: medir recall temporal de productos nuevos y cobertura primero.
