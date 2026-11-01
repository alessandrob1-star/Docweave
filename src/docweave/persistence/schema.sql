CREATE TABLE IF NOT EXISTS documents (
            document_id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
            workspace_label TEXT NOT NULL,
            original_directory TEXT NOT NULL,
            original_filename TEXT NOT NULL,
            current_directory TEXT NOT NULL,
            current_filename TEXT NOT NULL,
            content_sha256 BLOB NOT NULL,
            page_count INTEGER NULL CHECK (page_count IS NULL OR page_count > 0),
            status TEXT NOT NULL CHECK (
                status IN ('discovered', 'proposed', 'approved', 'rejected', 'moved')
            ),
            discovered_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_documents_workspace_content
                UNIQUE (workspace_label, content_sha256)
        );

CREATE TABLE IF NOT EXISTS agent_runs (
            agent_run_id TEXT PRIMARY KEY,
            document_id TEXT NOT NULL,
            provider TEXT NOT NULL,
            model_id TEXT NOT NULL,
            task TEXT NOT NULL,
            status TEXT NOT NULL CHECK (
                status IN ('started', 'succeeded', 'failed')
            ),
            started_at TEXT NOT NULL,
            completed_at TEXT NULL,
            input_sha256 BLOB NOT NULL,
            output_json TEXT NOT NULL,
            summary TEXT NOT NULL,
            CONSTRAINT fk_agent_runs_document
                FOREIGN KEY (document_id) REFERENCES documents (document_id)
                ON DELETE CASCADE
        );

CREATE TABLE IF NOT EXISTS proposals (
            proposal_id TEXT PRIMARY KEY,
            document_id TEXT NOT NULL,
            agent_run_id TEXT NOT NULL,
            proposed_category TEXT NOT NULL,
            proposed_directory TEXT NOT NULL,
            proposed_filename TEXT NOT NULL,
            confidence DECIMAL(8, 6) NOT NULL CHECK (
                confidence >= 0 AND confidence <= 1
            ),
            evidence_summary TEXT NOT NULL,
            status TEXT NOT NULL CHECK (
                status IN ('needs_review', 'approved', 'rejected')
            ),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_proposals_document
                FOREIGN KEY (document_id) REFERENCES documents (document_id)
                ON DELETE CASCADE,
            CONSTRAINT fk_proposals_agent_run
                FOREIGN KEY (agent_run_id) REFERENCES agent_runs (agent_run_id)
                ON DELETE CASCADE
        );

CREATE TABLE IF NOT EXISTS human_decisions (
            human_decision_id TEXT PRIMARY KEY,
            proposal_id TEXT NOT NULL,
            actor_label TEXT NOT NULL,
            decision TEXT NOT NULL CHECK (
                decision IN ('approve', 'reject', 'request_changes')
            ),
            reason TEXT NULL,
            decided_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_human_decisions_proposal
                FOREIGN KEY (proposal_id) REFERENCES proposals (proposal_id)
                ON DELETE CASCADE
        );

CREATE TABLE IF NOT EXISTS file_history (
            file_history_id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
            document_id TEXT NOT NULL,
            proposal_id TEXT NOT NULL,
            human_decision_id TEXT NOT NULL,
            event_sequence INTEGER NOT NULL,
            operation TEXT NOT NULL CHECK (
                operation IN ('move', 'rename', 'rename_and_move')
            ),
            previous_directory TEXT NOT NULL,
            previous_filename TEXT NOT NULL,
            next_directory TEXT NOT NULL,
            next_filename TEXT NOT NULL,
            status TEXT NOT NULL CHECK (
                status IN ('planned', 'succeeded', 'failed')
            ),
            occurred_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            note TEXT NULL,
            CONSTRAINT uq_file_history_document_sequence
                UNIQUE (document_id, event_sequence),
            CONSTRAINT fk_file_history_document
                FOREIGN KEY (document_id) REFERENCES documents (document_id)
                ON DELETE CASCADE,
            CONSTRAINT fk_file_history_proposal
                FOREIGN KEY (proposal_id) REFERENCES proposals (proposal_id)
                ON DELETE CASCADE,
            CONSTRAINT fk_file_history_decision
                FOREIGN KEY (human_decision_id)
                REFERENCES human_decisions (human_decision_id)
                ON DELETE CASCADE
        );

CREATE TABLE IF NOT EXISTS document_relationships (
            relationship_id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
            source_document_id TEXT NOT NULL,
            target_document_id TEXT NOT NULL,
            relationship_type TEXT NOT NULL,
            confidence DECIMAL(8, 6) NOT NULL CHECK (
                confidence >= 0 AND confidence <= 1
            ),
            evidence_summary TEXT NOT NULL,
            created_by_agent_run_id TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_relationship_agent_run
                FOREIGN KEY (created_by_agent_run_id)
                REFERENCES agent_runs (agent_run_id)
                ON DELETE CASCADE,
            CONSTRAINT fk_document_relationships_source
                FOREIGN KEY (source_document_id)
                REFERENCES documents (document_id)
                ON DELETE CASCADE,
            CONSTRAINT fk_document_relationships_target
                FOREIGN KEY (target_document_id)
                REFERENCES documents (document_id)
                ON DELETE CASCADE
        );

CREATE INDEX IF NOT EXISTS ix_documents_workspace_status
        ON documents (workspace_label, status);

CREATE INDEX IF NOT EXISTS ix_file_history_timeline
        ON file_history (document_id, occurred_at DESC);
