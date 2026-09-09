# Ground Truth del embudo

Anotación de los eventos de interacción **pick-up** (tomar producto) y
**put-back** (devolverlo) de la fuente de verdad, para validar con
**precisión / recall / F1** la detección automática del pipeline YOLO.

## Zonas vigentes

Los ids usados hoy por el pipeline (config de `app/config.py`):

- `Estante_Izquierdo`
- `Estante_Central`
- `Estante_Derecho`

Si un GT cita una zona que ya no existe en el pipeline, el validador avisa.

## Flujo rápido

1. Ejecutar el análisis (genera `outputs/metricas_retail.json`):

   ```bash
   python -m app.interfaces.cli --video video/videoBase.mp4 --no-ventana --guardar-frames outputs/vision_frames
   ```

2. Generar el **GT candidato** desde lo que el pipeline detectó (para
   revisar/editar en lugar de anotar todo a mano):

   ```bash
   python -m app.interfaces.generar_gt
   ```

3. Editar `ground_truth/candidatos.json`:
   - `frame`: corregir al fotograma exacto si el detector se desvió.
   - `tipo`: `pick_up` / `put_back`.
   - `zona`: id del pipeline, o `null` si no se exige zona concreta.

4. Validar coherencia + F1:

   ```bash
   python -m app.interfaces.validar_embudo --gt ground_truth/candidatos.json
   ```

   Para ver cuánto tolera el match (el detector y la percepción humana nunca
   pisan el mismo frame exacto) y elegir la ventana justa:

   ```bash
   python -m app.interfaces.validar_embudo --gt ground_truth/candidatos.json --barrido-tol
   python -m app.interfaces.validar_embudo --gt ground_truth/candidatos.json --tol 12
   ```

## Formato del GT

```json
{
  "video": "video/videoBase.mp4",
  "eventos": [
    { "frame": 150, "tipo": "pick_up", "zona": "Estante_Izquierdo" },
    { "frame": 210, "tipo": "put_back", "zona": "Estante_Central" }
  ]
}
```

`zona` es opcional: si se omite, el match no exige zona.

## Umbral que falla el proceso

Desde el pipeline, validando en el mismo comando que exporta (sale con código
de error si el F1 no cumple):

```bash
python -m app.interfaces.cli --video video/videoBase.mp4 \
    --gt ground_truth/candidatos.json --umbral-f1 0.8
```

Solo coherencia del JSON exportado (sin GT):

```bash
python -m app.interfaces.validar_embudo
```

## Notas

- El emparejamiento es greedy 1:1 por vecino más cercano (listas ordenadas
  por frame) dentro de la tolerancia, con desglose por zona.
- Si el GT tiene eventos en zonas obsoletas se avisa al validar.
- El generador (`generar_gt`) es un punto de partida: un video sin
  pick-ups/put-backs deja el GT vacío a propósito para anotar a mano.