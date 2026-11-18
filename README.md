# LocalHelp

Aplicación web educativa para buscar lugares comunitarios cercanos por ciudad, estado o código postal y categoría.

## Qué incluye

- Página web en español, adaptable a celular y computadora.
- API propia con FastAPI.
- Geocodificación de ciudad/código postal con Nominatim.
- Búsqueda de lugares en OpenStreetMap mediante Overpass API.
- Categorías: alimentación, vivienda/refugios, salud, educación, empleo y ayuda comunitaria.
- Mapa interactivo con Leaflet.
- Cálculo de distancia aproximada.
- SQLite para guardar caché de ubicaciones y solicitudes de demostración.
- Avisos de privacidad y limitaciones.

## Requisitos

- Python 3.10 o superior.
- Conexión a Internet para consultar los servicios de OpenStreetMap.

## Instalación en Windows

Abre PowerShell dentro de la carpeta `LocalHelp` y ejecuta:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
uvicorn backend.main:app --reload
```

Si PowerShell bloquea la activación, puedes ejecutar directamente:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload
```

Abre en el navegador:

- Página: http://127.0.0.1:8000
- Documentación interactiva de la API: http://127.0.0.1:8000/docs
- Estado de la API: http://127.0.0.1:8000/api/health

## Ejemplo de búsqueda

```text
Ciudad: Ogden, Utah
Categoría: Alimentación
Distancia: 10 km
```

También puedes buscar por código postal, por ejemplo `84401, Utah`.

## API

Ejemplo:

```http
GET /api/search?location=Ogden%2C%20Utah&category=food&radius_km=10
```

Categorías válidas: `food`, `housing`, `health`, `education`, `employment`, `community`.

## Fuente y limitaciones

Los resultados se consultan en OpenStreetMap usando Overpass. Son lugares que están etiquetados en los datos de OpenStreetMap, no un directorio oficial de beneficios. Puede haber recursos que no estén registrados, datos incompletos o información desactualizada. LocalHelp no confirma elegibilidad, cupos, horarios ni disponibilidad de ayuda. El usuario debe contactar a cada organización antes de acudir.

En Estados Unidos, el usuario también puede llamar al 211 para recibir orientación sobre servicios comunitarios.

## Uso responsable de servicios públicos

Nominatim es un servicio comunitario con capacidad limitada. Esta aplicación realiza geocodificación solo cuando el usuario envía una búsqueda, almacena en caché el resultado y envía un User-Agent identificable. Respeta su política vigente: https://operations.osmfoundation.org/policies/nominatim/

Overpass también es un servicio compartido y puede estar ocupado o limitar solicitudes. No uses esta configuración gratuita para tráfico alto o producción comercial sin elegir un proveedor apropiado o alojar tu propia infraestructura.

Mapa y datos: © OpenStreetMap contributors. Consulta https://www.openstreetmap.org/copyright

## Privacidad

No introduzcas direcciones particulares ni datos personales sensibles. La ubicación escrita se envía a los servicios de geocodificación y búsqueda para obtener resultados. La base SQLite de este proyecto se guarda localmente en `data/localhelp.db`.
