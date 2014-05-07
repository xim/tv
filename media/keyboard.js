(function(document) {
  // Script assumed loaded after elements matched by SELECTOR are present in
  // the DOM.
 
  // Old browsers, be gone!
  if (!document.querySelector || !document.addEventListener) return;

  // Settings
  var SELECTOR = 'dd a';
  var ACTIVE_CLASS = 'active';

  var _setClass = function($el, className) {
    if (!$el) return;
    $el.className = className;
    $el.parentElement
       .parentElement
       .querySelector('dt')
       .className = className;
  };

  var _toggleActive = function() {
    _setClass(STATE.activeEl, '');

    STATE.activeEl = STATE.candidates[STATE.activeIdx];
    _setClass(STATE.activeEl, ACTIVE_CLASS);
    STATE.activeEl.focus();
  };

  // Keyboard event handler
  var goLeft = function() {
    if (STATE.activeIdx === 0) return;

    STATE.activeIdx -= 1;
    _toggleActive();
  };
  var goUp = function() {
    if ([0, 1].indexOf(STATE.activeIdx) > -1) return;

    STATE.activeIdx -= 2;
    _toggleActive();
  };
  var goRight = function() {
    if (STATE.activeIdx === STATE.candidates.length - 1) return;

    STATE.activeIdx += 1;
    _toggleActive();
  };
  var goDown = function() {
    if (STATE.activeIdx == STATE.candidates.length - 1 ||
        STATE.activeIdx == STATE.candidates.length - 2) return;

    STATE.activeIdx += 2;
    _toggleActive();
  };

  var charHandlers = {
    'right': goRight,
    'left' : goLeft,
    'down' : goDown,
    'up'   : goUp,
    'h'    : goLeft,
    'j'    : goDown,
    'k'    : goUp,
    'l'    : goRight
  };

  var keycodeMap = {
    37: 'left',
    38: 'up',
    39: 'right',
    40: 'down'
  };


  var getKeyChar = function(e) {
    // Arrow keys does NOT trigger a `keypress` event
    if (e.type === 'keypress') {
      return String.fromCharCode(e.which).toLowerCase();
    }
    // Letters trigger both a `keydown` and a `keypress` event
    if (e.type === 'keydown') {
      // Since hjkl is not in keycodeMap, this will return undefined, and thus
      // prevent a double call to the keychar handler.
      return keycodeMap[e.which];
    }
  };

  var handleKeyEvent = function(e) {
    var char = getKeyChar(e);
    if (!char) {
      return;
    }
    if (charHandlers[char]) {
      charHandlers[char]();
      e.preventDefault();
    }
  };

  document.addEventListener('keypress', handleKeyEvent, false);
  document.addEventListener('keydown', handleKeyEvent, false);

  // The STATE
  var STATE = {
      candidates: document.querySelectorAll(SELECTOR),
      activeIdx: 0,
      activeEl: undefined
  }
  // Activate initial state
  _toggleActive();

})(document);
