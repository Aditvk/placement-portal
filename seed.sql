-- Seed Companies
INSERT OR IGNORE INTO companies (id, name, location, industry_focus) VALUES 
(1, 'Google', 'Mountain View, CA', 'Search & AI'),
(2, 'Meta', 'Menlo Park, CA', 'Social Media & VR'),
(3, 'Stripe', 'San Francisco, CA', 'Fintech'),
(4, 'Vercel', 'Remote', 'Cloud & Frontend DevTools'),
(5, 'Netflix', 'Los Gatos, CA', 'Entertainment Streaming');

-- Seed Applications
-- status options: 'Applied', 'In Progress', 'Offer', 'Rejected'
INSERT INTO applications (id, company_id, role_title, status, deadline_date, jd_match_score, application_link) VALUES
(1, 1, 'Software Engineer - L3', 'In Progress', '2026-05-28 23:59:00', 85.0, 'https://careers.google.com/jobs/results/12345'),
(2, 2, 'Frontend Developer', 'In Progress', '2026-06-01 23:59:00', 78.0, 'https://metacareers.com/jobs/67890'),
(3, 3, 'Backend Engineer', 'Rejected', '2026-05-15 12:00:00', 92.0, 'https://stripe.com/jobs/active'),
(4, 4, 'Design Engineer', 'Offer', '2026-05-30 23:59:00', 95.0, 'https://vercel.com/careers/999'),
(5, 5, 'Software Engineer - Platform', 'Applied', '2026-05-22 17:00:00', 0.0, 'https://netflix.com/careers/555'); -- Deadline tomorrow! Within 48 hours.

-- Seed Interview Rounds
INSERT INTO interview_rounds (id, application_id, round_number, round_type, scheduled_time, notes) VALUES
(1, 1, 1, 'Online Assessment', '2026-05-22 23:59:00', 'Google OA covering data structures and algorithms. Need to finish within 90 minutes. (Within 48 hours!)'),
(2, 2, 1, 'Technical Round', '2026-05-24 10:00:00', 'Meta Frontend Technical Round: React, System Design, Javascript fundamentals.'),
(3, 3, 1, 'Online Assessment', '2026-05-10 10:00:00', 'Stripe Backend OA - Completed, rejected after review.'),
(4, 4, 1, 'Final Round', '2026-05-19 14:00:00', 'Vercel Portfolio presentation and behavioral round. Success!');
