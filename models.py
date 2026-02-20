from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class Settings(db.Model):
    """
    Zentrale Konfiguration für die App. 
    """
    id = db.Column(db.Integer, primary_key=True)
    weekly_hours = db.Column(db.Float, default=39.0)
    # Speichert die aktiven Wochentage als Komma-separierter String (z.B. "0,1,2,3,4")
    active_weekdays = db.Column(db.String(20), default="0,1,2,3,4") 
    ho_quota_percent = db.Column(db.Integer, default=60)
    hide_weekends = db.Column(db.Boolean, default=True)
    default_start_time = db.Column(db.String(5), default="08:00")
    auto_convert_planned = db.Column(db.Boolean, default=True)

class CustomHoliday(db.Model):
    """
    Eigene freie Tage oder Sonderregeltage.
    """
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.String(10), nullable=False) # Format: YYYY-MM-DD
    name = db.Column(db.String(50), nullable=False)
    hours = db.Column(db.Float, nullable=True, default=0.0)

class WorkEntry(db.Model):
    """
    Die tatsächlichen Zeiteinträge.
    """
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.String(10), nullable=False, index=True) # Format: YYYY-MM-DD
    # 'home', 'office', 'planned', 'sick', 'vacation', 'dr', 'glz'
    type = db.Column(db.String(20), default="home") 
    start_time = db.Column(db.String(5), nullable=True) # Format: HH:MM
    end_time = db.Column(db.String(5), nullable=True)   # Format: HH:MM
    comment = db.Column(db.String(255), nullable=True)
    
    # Optionales Überschreiben des GLZ-Saldos an diesem Tag
    glz_override = db.Column(db.Float, nullable=True)