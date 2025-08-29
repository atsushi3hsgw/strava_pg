CREATE TABLE activities (
    id BIGINT PRIMARY KEY,
    athlete_id BIGINT,
    data JSONB,
    created_at TIMESTAMP DEFAULT now()
);
CREATE INDEX idx_activities_athlete_id ON activities(athlete_id);
CREATE INDEX idx_activities_created_at ON activities(created_at);