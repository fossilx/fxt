#=================================================================================(80)
#
#   fxt ;D
#
#=================================================================================(80)
"""
fxtapps: research

Project code, three tiers by how widely it is shared:

    fxt/research/                           every project (tracking, paths, lockbox)
    fxtapps/research/<group>/common/        shared code for projects within the same group
    fxtapps/research/<group>/<project>/     one project; data at runs/<group>/<project>/

Code moves up a tier only when a second consumer actually needs it.

Group and project names are slugs (lowercase, digits, underscores; start with a
letter). `common` and `cli` are reserved at both levels.
"""
