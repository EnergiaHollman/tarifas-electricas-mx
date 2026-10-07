-- Tipo de cambio USD/MXN de Banxico (SIE). Una fila por serie y fecha.
-- SF43718: FIX por fecha de determinación. SF60653: mismo valor por fecha de publicación en el DOF.
CREATE TABLE tipo_cambio (
  serie TEXT NOT NULL,
  fecha TEXT NOT NULL,
  valor REAL NOT NULL,
  obtenido_en INTEGER NOT NULL,
  PRIMARY KEY (serie, fecha)
);
