-- Tasas de referencia de Banxico (SIE). Una fila por serie y fecha.
-- SF331451: TIIE de Fondeo a un día hábil bancario.
CREATE TABLE tasa_referencia (
  serie TEXT NOT NULL,
  fecha TEXT NOT NULL,
  valor REAL NOT NULL,
  obtenido_en INTEGER NOT NULL,
  PRIMARY KEY (serie, fecha)
);
