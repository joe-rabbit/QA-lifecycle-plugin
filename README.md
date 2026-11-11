# QA Lifecycle

Claude plugin that turns a BRD into an understanding doc, test plan, test scenarios and test cases, with a human review gate after every stage and requirement traceability throughout.

## Install

Replace `OWNER/REPO` with this repository's path.

```
/plugin marketplace add OWNER/REPO
/plugin install qa-lifecycle@qa-lifecycle
```

To build a `.plugin` file for upload instead:

```
./build.sh        # writes dist/qa-lifecycle.plugin
```

## Layout

```
.claude-plugin/marketplace.json   marketplace listing
plugins/qa-lifecycle/             the Claude plugin (see its README)
build.sh                          packages the plugin as a .plugin file
```

Plugin documentation: [plugins/qa-lifecycle/README.md](plugins/qa-lifecycle/README.md)
