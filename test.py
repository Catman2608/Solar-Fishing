                    # Calculate Stopping Distance Based On Relative Velocity
                    stopping_distance2 = abs(relative_velocity) * stopping_distance
                    if left_x <= fish_x <= right_x:
                        # On-bar: Use Stopping-distance / Counter-thrust Logic
                        if error > stopping_distance2:
                            # Bar Is Left Of Fish Beyond Stopping Distance → Hold To Move Right
                            self.status_overlay.set_line(3, "Tracking:", "> (Chase)")
                            control_signal = 30
                        elif error < -stopping_distance2:
                            # Bar Is Right Of Fish Beyond Stopping Distance → Release To Move Left
                            self.status_overlay.set_line(3, "Tracking:", "< (Chase)")
                            control_signal = -30
                        else:
                            # Within Stopping Distance — Counter-thrust Based On Relative Velocity
                            if relative_velocity > 0:
                                # Bar Moving Right Relative To Fish → Release (Apply Left Thrust)
                                self.status_overlay.set_line(3, "Tracking:", "< (Relative)")
                                control_signal = -30
                            else:
                                # Bar Moving Left Relative To Fish → Hold (Apply Right Thrust)
                                self.status_overlay.set_line(3, "Tracking:", "> (Relative)")
                                control_signal = 30
                    else:
                        control_signal = kp * error + kd * relative_velocity
                        self.status_overlay.set_line(3, "Tracking:", "> (PD)" if control_signal > 0 else "< (PD)")
                else:
                    control_signal = error