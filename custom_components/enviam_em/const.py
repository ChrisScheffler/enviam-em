DOMAIN = "enviam_em"
DEFAULT_TARGET_URL = "https://energy-monitor-home.energiemanagement-enviam.de/overview"
CONTEXT_URL = "https://energy-monitor-home.energiemanagement-enviam.de/context"
ENERGY_FLOW_URL = "https://hems.kiwigrid.com/v11/energy-flow"
SCAN_INTERVAL_SECONDS =10

# Arbeit (Energie) pro Intervall für einen Zeitraum. Der Overview-Endpunkt
# liefert im Gegensatz zu /analytics/consumption zusätzlich Erzeugung
# (WorkProduced) und Einspeisung (WorkOut) der Gesamtanlage.
ANALYTICS_OVERVIEW_URL = "https://hems.kiwigrid.com/v11/analytics/overview"
# Abfrageparameter: Art der gelieferten Werte (Arbeit statt Leistung).
ANALYTICS_TYPE = "WORK"
# Der Analytics-Endpunkt liefert Tagesverläufe und wird deutlich seltener
# abgefragt als der Live-Energy-Flow.
ANALYTICS_SCAN_INTERVAL_SECONDS = 60

# Schlüssel, unter denen die Koordinatoren in hass.data[DOMAIN][entry_id] liegen.
DATA_ENERGY_COORDINATOR = "energy"
DATA_ANALYTICS_COORDINATOR = "analytics"

# Host der authentifizierten Übersichtsseite; wird geprüft, um einen
# erfolgreichen Login von einer weitergeleiteten Keycloak-Seite zu unterscheiden.
OVERVIEW_HOST = "energy-monitor-home.energiemanagement-enviam.de"

# Gerätemetadaten für die Geräteregistrierung.
DEVICE_NAME = "enviaM Energy Monitor"
MANUFACTURER = "enviaM / Kiwigrid"
MODEL = "Kiwigrid HEMS"

# Einheiten, wie sie von der Analytics-API geliefert werden.
UNIT_WATT_HOUR = "WATTHOUR"
UNIT_KILO_WATT_HOUR = "KILOWATTHOUR"
