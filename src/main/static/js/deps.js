import React from "./vendor/es-react/react.js"
import ReactDOM from "./vendor/es-react/react-dom.js"
import htm from "./vendor/htm.module.js"

const html = htm.bind(React.createElement);

const {useEffect, useState} = React;

export {
  React,
  ReactDOM,
  html,
  useEffect,
  useState,
}
