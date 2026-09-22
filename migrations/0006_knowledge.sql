-- NMOS Phase 4 (soft): who knows a fact. Annotations only; the packet marks them for the model.
ALTER TABLE assertion ADD COLUMN known_by text[];
ALTER TABLE assertion ADD COLUMN hidden_from text[];
