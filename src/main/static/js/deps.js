import React from "https://unpkg.com/es-react@latest/dev/react.js";
import ReactDOM from "https://unpkg.com/es-react@latest/dev/react-dom.js";
import PropTypes from "https://unpkg.com/es-react@latest/dev/prop-types.js";
import htm from "https://unpkg.com/htm@latest?module";

const html = htm.bind(React.createElement);

const {useEffect, useState} = React;

export {
  React,
  ReactDOM,
  PropTypes,
  html,
  useEffect,
  useState,
}
