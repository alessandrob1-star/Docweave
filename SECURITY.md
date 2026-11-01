# Security

DocWeave is a local, single-user desktop application. It does not provide
multi-user authentication, database encryption, or a network service for
other computers. Restrict access to document folders and the local database
using operating-system permissions and disk encryption.

Model traffic is limited to loopback HTTP. Proxies and redirects are disabled.
The model cannot execute file operations; the desktop requires human review.
Document text is untrusted data. Structured model output is validated against
the taxonomy and extracted evidence before becoming a proposal.

PDF previews can contain links. Opening an external link is a separate,
explicitly confirmed user action in the system browser; it is not required
for document processing. Do not approve links from untrusted documents.

Use copies of documents when testing rename and restore. Keep backups of
documents and SQLite memory together. Do not publish private PDFs, extracted
text, database files, or configuration containing sensitive information.

Report suspected vulnerabilities privately to the repository owner through a
contact method shown on their GitHub profile. Public bug reports must omit
private documents, paths, database contents, and personal information.

Automated tests and static checks do not establish a security certification.
