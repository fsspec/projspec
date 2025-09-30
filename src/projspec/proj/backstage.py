from projspec.proj import ProjectSpec


class BackstageCatalog(ProjectSpec):
    spec_doc = "https://backstage.io/docs/features/software-catalog/descriptor-format/"

    def match(self) -> bool:
        return "catalog-info.yaml" in self.proj.basenames

    # spec is "---"-separated list of entries, each of which has a "kind", and a "spec"
    # as well as general metadata. The spec normally has a "type" to tell you what we're
    # really talking about. Each entry should have "apiVersion: backstage.io/*"
    # where v1alpha1 is the only known version when this was written.
