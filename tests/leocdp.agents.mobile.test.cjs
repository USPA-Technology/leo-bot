const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { test } = require("node:test");

const source = fs.readFileSync(
  path.join(__dirname, "../resources/js/leocdp.agents.js"),
  "utf8"
);

function setupAgents({ width, reducedMotion, chatVisible = true }) {
  let quickActionClick;
  const scrollCalls = [];
  const sentQuestions = [];
  const humanMessages = [];
  const chat = {
    getClientRects: () => chatVisible ? [{}] : [],
    scrollIntoView: options => scrollCalls.push(["chat", options]),
  };
  const chatCard = {
    scrollIntoView: options => scrollCalls.push(["card", options]),
  };

  function jquery(subject) {
    if (typeof subject === "function") {
      subject();
      return;
    }

    let proxy;
    const stub = {
      length: 0,
      attr(name, value) {
        if (arguments.length === 1 && subject && subject.attributes) {
          return subject.attributes[name];
        }
        return proxy;
      },
      on(event, selector, handler) {
        if (subject === "#leobot_quick_actions") {
          quickActionClick = handler;
        }
        return proxy;
      },
    };
    proxy = new Proxy(stub, {
      get(target, property) {
        if (property in target) return target[property];
        return function () { return proxy; };
      },
    });
    return proxy;
  }

  jquery.getScript = function () {};

  const document = {
    getElementById(id) {
      if (id === "LEO_ChatBot_Container") return chat;
      if (id === "leobot_chat_container") return chatCard;
      return null;
    },
  };
  const window = {
    LEO_UI_LANGUAGE: "en",
    clearTimeout() {},
    getBotUI() {
      return { message: { human: message => humanMessages.push(message) } };
    },
    innerWidth: width,
    localStorage: { setItem() {} },
    location: { hostname: "localhost", protocol: "http:" },
    matchMedia(query) {
      return {
        matches: query.includes("prefers-reduced-motion")
          ? reducedMotion
          : width <= 991,
      };
    },
    sendQuestionToLeoAI(context, question) {
      sentQuestions.push({ context, question });
    },
    setTimeout() {
      return 1;
    },
    startLeoChatBot() {},
  };
  const context = vm.createContext({
    CDP_TRACKING: false,
    HOSTNAME: "localhost",
    document,
    jQuery: jquery,
    window,
  });
  vm.runInContext(source, context);

  return {
    clickQuickAction(question) {
      assert.equal(typeof quickActionClick, "function");
      quickActionClick.call({ attributes: { "data-question": question } });
    },
    humanMessages,
    scrollCalls,
    sentQuestions,
  };
}

test("quick actions scroll mobile users to the chat and send the prompt", () => {
  const app = setupAgents({ width: 390, reducedMotion: false });
  app.clickQuickAction("Find coffee nearby");

  assert.equal(JSON.stringify(app.scrollCalls), JSON.stringify([
    ["chat", { behavior: "smooth", block: "start" }],
  ]));
  assert.equal(JSON.stringify(app.sentQuestions), JSON.stringify([
    { context: "ask", question: "Find coffee nearby" },
  ]));
  assert.equal(
    JSON.stringify(app.humanMessages),
    JSON.stringify([{ content: "Find coffee nearby" }])
  );
});

test("uses the visible chat card if the chat surface is still hidden", () => {
  const app = setupAgents({
    width: 390,
    reducedMotion: true,
    chatVisible: false,
  });
  app.clickQuickAction("Find coffee nearby");

  assert.equal(JSON.stringify(app.scrollCalls), JSON.stringify([
    ["card", { behavior: "auto", block: "start" }],
  ]));
});

test("does not change page scroll on desktop", () => {
  const app = setupAgents({ width: 1280, reducedMotion: false });
  app.clickQuickAction("Find coffee nearby");

  assert.equal(app.scrollCalls.length, 0);
});
