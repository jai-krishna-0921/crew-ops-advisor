/**
 * Applies the stored theme choice before first paint.
 *
 * Three states, matching the theme rule in `globals.css`:
 *   "system"  no attribute, `prefers-color-scheme` decides
 *   "light"   data-theme="light"
 *   "dark"    data-theme="dark"
 *
 * Runs as a blocking inline script so there is no flash of the wrong theme
 * on a console someone opens at 6 a.m. in a dim room.
 */
const script = `(function(){try{var t=localStorage.getItem("crewops.theme");if(t==="light"||t==="dark"){document.documentElement.setAttribute("data-theme",t)}}catch(e){}})()`;

export function ThemeScript() {
  return <script dangerouslySetInnerHTML={{ __html: script }} />;
}
