const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { test } = require("node:test");

const source = fs.readFileSync(
  path.join(__dirname, "../resources/js/botui.js"),
  "utf8"
);

function setupBotUI(viewportWidth) {
  const directives = {};

  function Vue() {
    this.$children = [{}];
  }

  Vue.prototype.$mount = function () {
    return this;
  };
  Vue.directive = function (name, definition) {
    directives[name] = definition;
  };
  Vue.component = function () {};

  const window = { innerWidth: viewportWidth, Vue };
  const context = vm.createContext({
    window,
    document: { getElementById: function () { return {}; } },
    Promise,
    setTimeout,
  });
  vm.runInContext(source, context);
  new window.BotUI("chat", { fontawesome: false, searchselect: false });

  return directives;
}

test("does not autofocus chat inputs on mobile viewports", () => {
  const directives = setupBotUI(390);
  let focused = false;

  directives.focus.inserted({
    focus: function () {
      focused = true;
    },
  });

  assert.equal(focused, false);
});

test("keeps desktop autofocus behavior", () => {
  const directives = setupBotUI(1024);
  let focused = false;

  directives.focus.inserted({
    focus: function () {
      focused = true;
    },
  });

  assert.equal(focused, true);
});

test("scrolls the chat container without scrolling the page", () => {
  const directives = setupBotUI(390);
  const container = { scrollHeight: 900, scrollTop: 0 };
  let pageScrollRequested = false;

  directives["botui-container"].inserted(container);
  directives["botui-scroll"].inserted({
    scrollIntoView: function () {
      pageScrollRequested = true;
    },
  });

  assert.equal(container.scrollTop, 900);
  assert.equal(pageScrollRequested, false);
});
