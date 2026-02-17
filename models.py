from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class Settings(db.Model):
    """
    Zentrale Konfiguration für die App. 
    """
    id = db.Column(db.Integer, primary_key=True)
    weekly_hours = db.Column(db.Float, default=39.0)
    # Speichert die aktiven Wochentage als Komma-separierter String (z.B. "0,1,2,3,4" für Mo-Fr)
    active_weekdays = db.Column(db.String(20), default="0,1,2,3,4") 
    ho_quota_percent = db.Column(db.Integer, default=60)
    hide_weekends = db.Column(db.Boolean, default=True)
    
    # Felder für die Automatisierung
    default_start_time = db.Column(db.String(5), default="08:00")
    
    # Schalter: Soll 'planned' automatisch in 'home' gewandelt werden, wenn der Tag vorbei ist?
    auto_convert_planned = db.Column(db.Boolean, default=True)

class CustomHoliday(db.Model):
    """
    Eigene freie Tage oder Sonderregeltage (z.B. Wäldchestag, Betriebsausflug).
    """
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.String(10), nullable=False) # Format: YYYY-MM-DD
    name = db.Column(db.String(50), nullable=False)
    hours = db.Column(db.Float, nullable=True, default=0.0) # Soll-Stunden an diesem Tag (0 = Frei)

class WorkEntry(db.Model):
    """
    Die tatsächlichen Zeiteinträge.
    """
    id = db.Column(db.Integer, primary_key=True)
    
    # Datum des Eintrags. Nicht unique, da wir Split-Shifts (z.B. Vormittag/Nachmittag) erlauben.
    date = db.Column(db.String(10), nullable=False, index=True) # Format: YYYY-MM-DD
    
    # Typen: 
    # 'home'    = Home Office (Ist)
    # 'office'  = Büro (Ist)
    # 'planned' = Geplanter HO-Tag (Vorschau/Planung) -> Ehemals 'x'
    # 'sick'    = Krank
    # 'vacation'= Urlaub
    # 'dr'      = Dienstreise
    # 'glz'     = Gleitzeitabbau
    type = db.Column(db.String(20), default="home") 
    
    start_time = db.Column(db.String(5), nullable=True) # Format: HH:MM
    end_time = db.Column(db.String(5), nullable=True)   # Format: HH:MM
    
    # Speichert Notizen (z.B. "Vormittagsblock", "Arzttermin")
    comment = db.Column(db.String(255), nullable=True)